import unittest
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

CAPABILITIES_PATH = Path(__file__).parents[1] / "custom_components" / "electrolux" / "capabilities.py"
SPEC = spec_from_file_location("electrolux_capabilities", CAPABILITIES_PATH)
capabilities = module_from_spec(SPEC)
sys.modules[SPEC.name] = capabilities
SPEC.loader.exec_module(capabilities)

capabilities_from_json = capabilities.capabilities_from_json
command_body_for_capability = capabilities.command_body_for_capability


class CapabilitiesTest(unittest.TestCase):
    def test_legacy_capability_fields_are_preserved(self):
        info = capabilities_from_json(
            {
                "applianceInfo": {
                    "serialNumber": "123",
                    "pnc": "456",
                    "brand": "AEG",
                    "deviceType": "PORTABLE_AIR_CONDITIONER",
                    "model": "model",
                    "variant": "variant",
                    "colour": "white",
                },
                "capabilities": {
                    "targetTemperatureC": {
                        "access": "readwrite",
                        "type": "temperature",
                        "min": 16,
                        "max": 30,
                        "step": 0.5,
                        "disabled": False,
                        "default": 22,
                        "schedulable": True,
                    }
                },
            }
        )

        capability = info.capabilities["targetTemperatureC"]

        self.assertEqual(capability.type, "temperature")
        self.assertTrue(capability.access.can_write)
        self.assertEqual(capability.min, 16)
        self.assertEqual(capability.max, 30)
        self.assertEqual(capability.step, 0.5)
        self.assertEqual(capability.default, 22)
        self.assertTrue(capability.schedulable)

    def test_dam_capabilities_are_flattened(self):
        info = capabilities_from_json(
            {
                "dataModelVersion": "DAM-1.0.0",
                "applianceInfo": {"deviceType": "AIR_PURIFIER"},
                "capabilities": {
                    "airConditioner": {
                        "type": "object",
                        "mode": {
                            "access": "readwrite",
                            "type": "string",
                            "values": {"auto": {}, "cool": {}},
                        },
                    }
                },
            }
        )

        self.assertIn("airConditioner.mode", info.capabilities)
        self.assertEqual(info.capabilities["airConditioner.mode"].values, ("auto", "cool"))

    def test_triggers_update_runtime_capability(self):
        info = capabilities_from_json(
            {
                "applianceInfo": {"deviceType": "PORTABLE_AIR_CONDITIONER"},
                "capabilities": {
                    "mode": {
                        "access": "readwrite",
                        "type": "string",
                        "values": {"FANONLY": {}, "COOL": {}},
                        "triggers": [
                            {
                                "condition": {"operand_1": "value", "operator": "eq", "operand_2": "FANONLY"},
                                "action": {"targetTemperatureC": {"disabled": True, "access": "read"}},
                            }
                        ],
                    },
                    "targetTemperatureC": {"access": "readwrite", "type": "temperature", "min": 16, "max": 30},
                },
            }
        )

        runtime = info.runtime_capabilities({"mode": "FANONLY", "targetTemperatureC": 21})

        self.assertTrue(runtime["targetTemperatureC"].disabled)
        self.assertFalse(runtime["targetTemperatureC"].can_write)

    def test_workmode_auto_disables_fanspeed(self):
        info = capabilities_from_json(
            {
                "applianceInfo": {"deviceType": "AIR_PURIFIER"},
                "capabilities": {
                    "Workmode": {
                        "access": "readwrite",
                        "type": "string",
                        "values": {"Auto": {}, "Manual": {}, "PowerOff": {}},
                        "triggers": [
                            {
                                "condition": {"operand_1": "value", "operand_2": "Auto", "operator": "eq"},
                                "action": {
                                    "Fanspeed": {
                                        "access": "readwrite",
                                        "disabled": True,
                                        "max": 5,
                                        "min": 1,
                                        "step": 1,
                                        "type": "int",
                                    }
                                },
                            }
                        ],
                    },
                    "Fanspeed": {"access": "readwrite", "type": "int", "min": 1, "max": 5, "step": 1},
                },
            }
        )

        runtime = info.runtime_capabilities({"Workmode": "Auto", "Fanspeed": 3})

        self.assertTrue(runtime["Fanspeed"].disabled)
        self.assertFalse(runtime["Fanspeed"].can_write)

    def test_ac_fanonly_limits_fan_speed_setting(self):
        info = capabilities_from_json(
            {
                "applianceInfo": {"deviceType": "PORTABLE_AIR_CONDITIONER"},
                "capabilities": {
                    "mode": {
                        "access": "readwrite",
                        "type": "string",
                        "values": {"AUTO": {}, "COOL": {}, "FANONLY": {}},
                        "triggers": [
                            {
                                "condition": {"operand_1": "value", "operator": "eq", "operand_2": "FANONLY"},
                                "action": {
                                    "fanSpeedSetting": {
                                        "access": "readwrite",
                                        "type": "string",
                                        "values": {"HIGH": {}, "LOW": {}, "MIDDLE": {}},
                                    },
                                    "targetTemperatureC": {
                                        "access": "readwrite",
                                        "disabled": True,
                                        "type": "temperature",
                                    },
                                },
                            }
                        ],
                    },
                    "fanSpeedSetting": {
                        "access": "readwrite",
                        "type": "string",
                        "values": {"AUTO": {}, "HIGH": {}, "LOW": {}, "MIDDLE": {}},
                    },
                    "fanSpeedState": {"access": "read", "type": "string", "values": {"HIGH": {}, "LOW": {}, "MIDDLE": {}}},
                    "targetTemperatureC": {"access": "readwrite", "type": "temperature", "min": 16, "max": 30},
                },
            }
        )

        runtime = info.runtime_capabilities({"mode": "FANONLY", "fanSpeedSetting": "auto"})

        self.assertEqual(runtime["fanSpeedSetting"].values, ("HIGH", "LOW", "MIDDLE"))
        self.assertNotIn("AUTO", {value.upper() for value in runtime["fanSpeedSetting"].values})
        self.assertEqual(runtime["fanSpeedSetting"].values[0], "HIGH")

    def test_command_body_for_legacy_and_dam(self):
        legacy_info = capabilities_from_json(
            {
                "applianceInfo": {"deviceType": "PORTABLE_AIR_CONDITIONER"},
                "capabilities": {"targetTemperatureC": {"access": "readwrite", "type": "temperature"}},
            }
        )
        dam_info = capabilities_from_json(
            {
                "applianceInfo": {"deviceType": "PORTABLE_AIR_CONDITIONER"},
                "capabilities": {
                    "airConditioner": {
                        "type": "object",
                        "mode": {"access": "readwrite", "type": "string"},
                    }
                },
            }
        )

        self.assertEqual(
            command_body_for_capability(legacy_info.capabilities["targetTemperatureC"], 20, is_dam=False),
            {"targetTemperatureC": 20},
        )
        self.assertEqual(
            command_body_for_capability(dam_info.capabilities["airConditioner.mode"], "cool", is_dam=True),
            {"commands": [{"airConditioner": {"mode": "cool"}}]},
        )


if __name__ == "__main__":
    unittest.main()
