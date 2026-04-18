"""
Unit tests for the dual-frequency datacollection refactor.

Covers:
  - IntervalGroup wildcard expansion (TaskScheduler._resolve_interval_groups)
  - param_filter propagation in ImprovedDataCollectionManager.collect_data_for_building
  - PDU_CHUNK_SIZE chunking in PLCManager._read_single_plc_multiple_params
  - byte data_type parsing in PLCReadWriter._parse_data
  - Connection reuse: PLCManager.clients_cache is used across calls

Run with:
    python -m pytest tests/test_datacollection_refactor.py -v
"""

import sys
import os
import json
import struct
import threading
import types
import unittest
from unittest.mock import MagicMock, patch, call

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Helpers: stub out snap7 so PLCReadWriter can be imported without the library
# ---------------------------------------------------------------------------

def _make_snap7_stub():
    snap7_mod = types.ModuleType("snap7")
    client_mod = types.ModuleType("snap7.client")

    class FakeClient:
        def connect(self, *a, **kw): pass
        def get_connected(self): return True
        def disconnect(self): pass
        def db_read(self, db_num, offset, length): return b'\x00' * length
        def read_multi(self, requests):
            return [(True, b'\x00' * req[3]) for req in requests]

    client_mod.Client = FakeClient
    snap7_mod.client = client_mod
    return snap7_mod


if 'snap7' not in sys.modules:
    sys.modules['snap7'] = _make_snap7_stub()
    sys.modules['snap7.client'] = sys.modules['snap7'].client


# ---------------------------------------------------------------------------
# Now safe to import project modules
# ---------------------------------------------------------------------------
from datacollection.multi_thread_plc_handler import PLCReadWriter, PLCManager, PDU_CHUNK_SIZE
from datacollection.task_scheduler import IntervalGroup, TaskScheduler


# ---------------------------------------------------------------------------
# Test: byte data_type parsing
# ---------------------------------------------------------------------------

class TestPLCReadWriterParseByte(unittest.TestCase):
    def setUp(self):
        self.rw = PLCReadWriter.__new__(PLCReadWriter)

    def test_byte_parses_unsigned_int(self):
        raw = struct.pack('>B', 42)
        result = self.rw._parse_data(raw, 'byte')
        self.assertEqual(result, 42)

    def test_byte_max_value(self):
        raw = struct.pack('>B', 255)
        result = self.rw._parse_data(raw, 'byte')
        self.assertEqual(result, 255)

    def test_byte_wrong_length_returns_none(self):
        result = self.rw._parse_data(b'\x00\x00', 'byte')
        self.assertIsNone(result)

    def test_int16_still_works(self):
        raw = struct.pack('>h', -100)
        result = self.rw._parse_data(raw, 'int16')
        self.assertEqual(result, -100)

    def test_int32_still_works(self):
        raw = struct.pack('>i', 999999)
        result = self.rw._parse_data(raw, 'int32')
        self.assertEqual(result, 999999)


# ---------------------------------------------------------------------------
# Test: PDU chunking in PLCManager._read_single_plc_multiple_params
# ---------------------------------------------------------------------------

class TestPLCManagerChunking(unittest.TestCase):
    def setUp(self):
        self.manager = PLCManager(max_workers=2)
        self.manager.start()

    def tearDown(self):
        self.manager.stop()

    def _make_configs(self, count: int):
        """Build `count` dummy read configs all on db_num=14."""
        return [
            {'ip': '10.0.0.1', 'db_num': 14, 'offset': i * 2, 'length': 2, 'data_type': 'int16'}
            for i in range(count)
        ]

    def test_chunk_size_constant_is_12(self):
        self.assertEqual(PDU_CHUNK_SIZE, 12)

    def test_single_chunk_when_params_lte_chunk_size(self):
        configs = self._make_configs(PDU_CHUNK_SIZE)  # exactly 12
        read_multi_calls = []

        def fake_read_multi(self_rw, requests, max_retries=2):
            read_multi_calls.append(len(requests))
            return [(True, "读取成功", 0)] * len(requests)

        with patch.object(PLCReadWriter, 'read_multi', fake_read_multi):
            results = self.manager._read_single_plc_multiple_params('10.0.0.1', configs)

        self.assertEqual(len(read_multi_calls), 1,
                         "Should issue exactly 1 read_multi call for <= CHUNK_SIZE params")
        self.assertEqual(len(results), PDU_CHUNK_SIZE)

    def test_multiple_chunks_when_params_gt_chunk_size(self):
        param_count = PDU_CHUNK_SIZE * 2 + 3  # 27
        configs = self._make_configs(param_count)
        read_multi_calls = []

        def fake_read_multi(self_rw, requests, max_retries=2):
            read_multi_calls.append(len(requests))
            return [(True, "读取成功", 0)] * len(requests)

        with patch.object(PLCReadWriter, 'read_multi', fake_read_multi):
            results = self.manager._read_single_plc_multiple_params('10.0.0.1', configs)

        expected_chunks = 3  # ceil(27 / 12) = 3
        self.assertEqual(len(read_multi_calls), expected_chunks,
                         f"Expected {expected_chunks} chunks for {param_count} params")
        self.assertEqual(len(results), param_count)
        # First two chunks are full, last has the remainder
        self.assertEqual(read_multi_calls[0], PDU_CHUNK_SIZE)
        self.assertEqual(read_multi_calls[1], PDU_CHUNK_SIZE)
        self.assertEqual(read_multi_calls[2], 3)

    def test_chunk_failure_does_not_abort_other_chunks(self):
        """A single chunk failure should mark those params as failed but not stop other chunks."""
        configs = self._make_configs(PDU_CHUNK_SIZE + 1)  # 13 params → 2 chunks
        call_count = [0]

        def fake_read_multi(self_rw, requests, max_retries=2):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("simulated PDU error")
            return [(True, "读取成功", 0)] * len(requests)

        with patch.object(PLCReadWriter, 'read_multi', fake_read_multi):
            results = self.manager._read_single_plc_multiple_params('10.0.0.1', configs)

        self.assertEqual(len(results), PDU_CHUNK_SIZE + 1)
        # First chunk (12 items) should be failures
        for r in results[:PDU_CHUNK_SIZE]:
            self.assertFalse(r['success'])
        # Second chunk (1 item) should succeed
        self.assertTrue(results[PDU_CHUNK_SIZE]['success'])


# ---------------------------------------------------------------------------
# Test: PLCManager connection reuse (clients_cache)
# ---------------------------------------------------------------------------

class TestPLCManagerConnectionReuse(unittest.TestCase):
    def setUp(self):
        self.manager = PLCManager(max_workers=2)
        self.manager.start()

    def tearDown(self):
        self.manager.stop()

    def test_same_ip_reuses_reader_object(self):
        reader1 = self.manager._get_or_create_reader('10.0.0.2')
        reader2 = self.manager._get_or_create_reader('10.0.0.2')
        self.assertIs(reader1, reader2, "Same IP should return the same cached PLCReadWriter")

    def test_different_ips_get_different_readers(self):
        reader1 = self.manager._get_or_create_reader('10.0.0.3')
        reader2 = self.manager._get_or_create_reader('10.0.0.4')
        self.assertIsNot(reader1, reader2)

    def test_connect_called_once_across_two_collection_rounds(self):
        """connect() must succeed and reader must remain connected between rounds."""
        ip = '10.0.0.5'
        connect_calls = [0]
        original_connect = PLCReadWriter.connect

        def counting_connect(self_rw):
            connect_calls[0] += 1
            self_rw.connected = True
            return True

        configs = [{'ip': ip, 'db_num': 14, 'offset': 0, 'length': 2, 'data_type': 'int16'}]

        def fake_read_multi(self_rw, requests, max_retries=2):
            return [(True, "读取成功", 0)] * len(requests)

        with patch.object(PLCReadWriter, 'connect', counting_connect), \
             patch.object(PLCReadWriter, 'read_multi', fake_read_multi):
            self.manager._read_single_plc_multiple_params(ip, configs)
            self.manager._read_single_plc_multiple_params(ip, configs)  # second round

        # connect() on a PLCReadWriter that is already connected should return True immediately
        # without incrementing the counter a second time (see PLCReadWriter.connect guard)
        # Our counting_connect sets connected=True on first call; second call hits the early-return.
        self.assertEqual(connect_calls[0], 1,
                         "connect() should only execute once when connection is kept alive")


# ---------------------------------------------------------------------------
# Test: IntervalGroup wildcard expansion in TaskScheduler
# ---------------------------------------------------------------------------

class TestIntervalGroupWildcardExpansion(unittest.TestCase):
    def _make_scheduler_with_config(self, config_dict: dict) -> TaskScheduler:
        scheduler = TaskScheduler.__new__(TaskScheduler)
        scheduler.config = config_dict
        scheduler.stop_event = threading.Event()
        scheduler.group_threads = []
        scheduler.data_collection_manager = None
        return scheduler

    def _patch_param_names(self, scheduler, param_names: set):
        scheduler._load_all_param_names = lambda: param_names

    def test_wildcard_group_receives_non_named_params(self):
        all_params = {'a', 'b', 'c', 'd', 'total_hot_quantity', 'total_cold_quantity'}
        config = {
            "scheduler": {
                "interval_seconds": 300,
                "building_files": [],
                "interval_groups": [
                    {"name": "energy", "interval_seconds": 300,
                     "param_names": ["total_hot_quantity", "total_cold_quantity"]},
                    {"name": "general", "interval_seconds": 600,
                     "param_names": ["*"]}
                ]
            }
        }
        scheduler = self._make_scheduler_with_config(config)
        self._patch_param_names(scheduler, all_params)

        groups = scheduler._resolve_interval_groups()

        energy_group = next(g for g in groups if g.name == 'energy')
        general_group = next(g for g in groups if g.name == 'general')

        self.assertEqual(set(energy_group.param_names),
                         {'total_hot_quantity', 'total_cold_quantity'})
        self.assertEqual(set(general_group.param_names), {'a', 'b', 'c', 'd'})

    def test_no_interval_groups_falls_back_to_single_group(self):
        config = {
            "scheduler": {
                "interval_seconds": 300,
                "building_files": []
            }
        }
        scheduler = self._make_scheduler_with_config(config)
        self._patch_param_names(scheduler, {'x', 'y'})

        groups = scheduler._resolve_interval_groups()
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].interval_seconds, 300)
        self.assertIn('*', groups[0].param_names)

    def test_wildcard_only_config(self):
        all_params = {'p1', 'p2', 'p3'}
        config = {
            "scheduler": {
                "interval_seconds": 600,
                "building_files": [],
                "interval_groups": [
                    {"name": "all", "interval_seconds": 600, "param_names": ["*"]}
                ]
            }
        }
        scheduler = self._make_scheduler_with_config(config)
        self._patch_param_names(scheduler, all_params)

        groups = scheduler._resolve_interval_groups()
        self.assertEqual(len(groups), 1)
        self.assertEqual(set(groups[0].param_names), all_params)


# ---------------------------------------------------------------------------
# Test: param_filter in collect_data_for_building
# ---------------------------------------------------------------------------

class TestCollectDataParamFilter(unittest.TestCase):
    """Test that param_filter correctly restricts which params are read."""

    def _make_manager(self):
        """Create ImprovedDataCollectionManager with all I/O mocked out."""
        # Import here to avoid circular import issues at module level
        from datacollection.improved_data_collection_manager import ImprovedDataCollectionManager
        mgr = ImprovedDataCollectionManager.__new__(ImprovedDataCollectionManager)
        mgr.max_workers = 2
        mgr.resource_dir = '/fake/resource'
        mgr.output_dir = '/fake/output'
        mgr.results = {}

        # Stub PLCManager
        fake_plc_manager = MagicMock()
        fake_plc_manager.thread_pool = MagicMock()
        mgr.plc_manager = fake_plc_manager
        return mgr

    def test_param_filter_none_collects_all_params(self):
        from datacollection.improved_data_collection_manager import ImprovedDataCollectionManager
        mgr = self._make_manager()

        full_plc_config = {
            'total_hot_quantity': {'db_num': 14, 'offset': 442, 'length': 4, 'data_type': 'int32'},
            'total_cold_quantity': {'db_num': 14, 'offset': 448, 'length': 4, 'data_type': 'int32'},
            'living_room_temperature': {'db_num': 14, 'offset': 1324, 'length': 2, 'data_type': 'int16'},
        }
        building_data = {
            'dev001': {'PLC IP地址': '10.0.0.10', 'IP地址': '10.0.0.10'}
        }

        collected_params = []

        def fake_read_all(configs):
            for c in configs:
                collected_params.append(c['param_key'])
            return [{'ip': c['ip'], 'device_id': c['device_id'], 'param_key': c['param_key'],
                     'success': True, 'message': 'ok', 'value': 0} for c in configs]

        mgr.load_building_json = lambda f: building_data
        mgr.load_plc_config = lambda: full_plc_config
        mgr.load_output_config = lambda: {'output': {'type': 'none', 'json': {'enabled': False},
                                                      'excel': {'enabled': False},
                                                      'mqtt': {'enabled': False}}}
        mgr._read_all_plc_data = fake_read_all

        mgr.collect_data_for_building('test.json', param_filter=None)
        self.assertEqual(set(collected_params), set(full_plc_config.keys()))

    def test_param_filter_set_restricts_params(self):
        from datacollection.improved_data_collection_manager import ImprovedDataCollectionManager
        mgr = self._make_manager()

        full_plc_config = {
            'total_hot_quantity': {'db_num': 14, 'offset': 442, 'length': 4, 'data_type': 'int32'},
            'total_cold_quantity': {'db_num': 14, 'offset': 448, 'length': 4, 'data_type': 'int32'},
            'living_room_temperature': {'db_num': 14, 'offset': 1324, 'length': 2, 'data_type': 'int16'},
        }
        building_data = {
            'dev001': {'PLC IP地址': '10.0.0.10', 'IP地址': '10.0.0.10'}
        }
        energy_filter = {'total_hot_quantity', 'total_cold_quantity'}

        collected_params = []

        def fake_read_all(configs):
            for c in configs:
                collected_params.append(c['param_key'])
            return [{'ip': c['ip'], 'device_id': c['device_id'], 'param_key': c['param_key'],
                     'success': True, 'message': 'ok', 'value': 0} for c in configs]

        mgr.load_building_json = lambda f: building_data
        mgr.load_plc_config = lambda: full_plc_config
        mgr.load_output_config = lambda: {'output': {'type': 'none', 'json': {'enabled': False},
                                                      'excel': {'enabled': False},
                                                      'mqtt': {'enabled': False}}}
        mgr._read_all_plc_data = fake_read_all

        mgr.collect_data_for_building('test.json', param_filter=energy_filter)
        self.assertEqual(set(collected_params), energy_filter)

    def test_param_filter_with_nonexistent_params_returns_empty(self):
        from datacollection.improved_data_collection_manager import ImprovedDataCollectionManager
        mgr = self._make_manager()

        full_plc_config = {
            'total_hot_quantity': {'db_num': 14, 'offset': 442, 'length': 4, 'data_type': 'int32'},
        }
        building_data = {'dev001': {'PLC IP地址': '10.0.0.10', 'IP地址': '10.0.0.10'}}

        mgr.load_building_json = lambda f: building_data
        mgr.load_plc_config = lambda: full_plc_config

        result = mgr.collect_data_for_building('test.json',
                                                param_filter={'nonexistent_param'})
        self.assertEqual(result, {})


# ---------------------------------------------------------------------------
# Test: plc_config.json (datacollection/resource) has all expected params
# ---------------------------------------------------------------------------

class TestPlcConfigFile(unittest.TestCase):
    def _load_config(self) -> dict:
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'datacollection', 'resource', 'plc_config.json'
        )
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def test_config_has_energy_params(self):
        cfg = self._load_config()
        params = cfg['parameters']
        self.assertIn('total_hot_quantity', params)
        self.assertIn('total_cold_quantity', params)

    def test_config_has_at_least_70_params(self):
        cfg = self._load_config()
        self.assertGreaterEqual(len(cfg['parameters']), 70)

    def test_config_has_room_params(self):
        cfg = self._load_config()
        params = cfg['parameters']
        self.assertIn('living_room_temperature', params)
        self.assertIn('bedroom_temperature', params)
        self.assertIn('study_room_temperature', params)

    def test_config_has_fault_params(self):
        cfg = self._load_config()
        params = cfg['parameters']
        self.assertIn('fresh_air_fault_status', params)
        self.assertIn('hydraulic_module_low_temp_error', params)

    def test_all_params_have_required_fields(self):
        cfg = self._load_config()
        required = {'name', 'db_num', 'offset', 'length', 'data_type'}
        for param_name, param_info in cfg['parameters'].items():
            missing = required - set(param_info.keys())
            self.assertEqual(missing, set(),
                             f"Parameter '{param_name}' missing fields: {missing}")


# ---------------------------------------------------------------------------
# Test: task_scheduler_config.json has interval_groups
# ---------------------------------------------------------------------------

class TestTaskSchedulerConfig(unittest.TestCase):
    def _load_config(self) -> dict:
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'resource', 'task_scheduler_config.json'
        )
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def test_interval_groups_present(self):
        cfg = self._load_config()
        self.assertIn('interval_groups', cfg['scheduler'])

    def test_energy_group_has_300s(self):
        cfg = self._load_config()
        groups = cfg['scheduler']['interval_groups']
        energy = next((g for g in groups if g['name'] == 'energy'), None)
        self.assertIsNotNone(energy, "energy group should exist")
        self.assertEqual(energy['interval_seconds'], 300)
        self.assertIn('total_hot_quantity', energy['param_names'])
        self.assertIn('total_cold_quantity', energy['param_names'])

    def test_general_group_has_600s_and_wildcard(self):
        cfg = self._load_config()
        groups = cfg['scheduler']['interval_groups']
        general = next((g for g in groups if g['name'] == 'general'), None)
        self.assertIsNotNone(general, "general group should exist")
        self.assertEqual(general['interval_seconds'], 600)
        self.assertIn('*', general['param_names'])

    def test_legacy_interval_seconds_present(self):
        cfg = self._load_config()
        self.assertIn('interval_seconds', cfg['scheduler'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
