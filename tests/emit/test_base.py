from __future__ import annotations

from fairypcbot.emit.easyeda_std import EasyedaStdEmitter
from fairypcbot.emit.specctra_dsn import SpecctraDsnEmitter


def test_easyeda_std_capabilities():
    caps = EasyedaStdEmitter().capabilities()
    assert caps.max_layers == 2
    assert "clearance" in caps.supports_rules


def test_specctra_dsn_capabilities():
    caps = SpecctraDsnEmitter().capabilities()
    assert caps.max_layers == 2
    assert "trace_width" in caps.supports_rules
