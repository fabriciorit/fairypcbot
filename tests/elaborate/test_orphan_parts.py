from __future__ import annotations

from fairypcbot.elaborate.checks.orphan_parts import check_orphan_parts
from fairypcbot.schemas.error_codes import ErrorCode
from fairypcbot.schemas.ir import Net, Netlist, NetMember, ResolvedPart


def _netlist(with_c12_wired: bool) -> Netlist:
    nets = {
        "OUT": Net(name="OUT", members=[NetMember(designator="U1"), NetMember(designator="R7")]),
    }
    if with_c12_wired:
        nets["ZOBEL_MID"] = Net(
            name="ZOBEL_MID", members=[NetMember(designator="R7"), NetMember(designator="C12")]
        )
    return Netlist(
        parts={
            "U1": ResolvedPart(designator="U1", class_id=None),
            "R7": ResolvedPart(designator="R7", class_id=None),
            "C12": ResolvedPart(designator="C12", class_id=None),
        },
        nets=nets,
    )


def test_flags_part_absent_from_all_nets():
    """Reprodução do caso real do BFO (see the documentation): C12 da rede Zobel fora de todas as nets."""
    warnings = check_orphan_parts(_netlist(with_c12_wired=False))
    assert len(warnings) == 1
    assert warnings[0].code == ErrorCode.W_PART_NOT_IN_ANY_NET
    assert "C12" in warnings[0].message


def test_silent_when_all_parts_wired():
    assert check_orphan_parts(_netlist(with_c12_wired=True)) == []
