"""Importers return a valid object or raise a documented error -- nothing else, on any input.

The readers take files that SymQ did not write. A reader that lets ``ValueError: Exceeds the
limit (4300 digits)``, ``RecursionError`` or a bare ``ValueError`` from ``Circuit.append`` escape
forces every caller to catch ``Exception``, and a broad ``except`` is how a real defect gets
reported as "bad input". The contracts checked here:

* ``parse_qasm`` / ``load_qasm``: a valid ``Circuit``, or ``QasmSyntaxError`` /
  ``UnsupportedOperation`` (both ``SymqError``);
* ``parse_kmx`` / ``load_kmx``: a ``KmxProgram``, or the same two errors;
* ``parse_circuit(data, name)``: a valid ``Circuit``, or a ``ValueError`` prefixed with ``name``.

Property tests explore arbitrary text, grammar-shaped token soups and mutations of valid programs.
A generated circuit written as OpenQASM 2 or 3 must parse back to itself: the generator is the
independent reference. The named cases at the end are the leaks found when these properties were
first run.
"""
from __future__ import annotations

import json

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from symq import Circuit, QasmSyntaxError, SymqError, UnsupportedOperation, load_qasm, parse_qasm
from symq.circuit import parse_circuit
from symq.kickmix import KmxProgram, KmxSyntaxError, load_kmx, parse_kmx
from symq.qasm import MAX_INDEX, bounded_index

REFUSALS = (QasmSyntaxError, UnsupportedOperation)
SETTINGS = settings(max_examples=300, deadline=None)

QASM_TOKENS = [
    "OPENQASM", "2.0", "3.0", "3", ";", "\n", " ", ",", "include", '"qelib1.inc"',
    '"stdgates.inc"', "qreg", "qubit", "q", "r", "[", "]", "(", ")", "@", "ctrl", "negctrl",
    "inv", "x", "cx", "ccx", "mcx", "h", "measure", "creg", "barrier", "//", "/*", "*/",
    "// i 0 1", "// o 1 0", "0", "1", "2", "7", "00", "-1", "9" * 12, "9" * 5000, "٣", "１",
    "q[0]", "q[1]", "q[2]", "q[99]", "\x00", "é", "\t",
]
KMX_TOKENS = [
    "X", "CX", "CCX", "SWAP", "CSWAP", "Z", "CZ", "CCZ", "HMR", "R", "Z_POW", "CX_IF",
    "REGISTER", "APPEND_TO_REGISTER", "INFO_TAG", "if", "#", '"label"', "\n", " ", "q0", "q1",
    "q2", "q7", "b0", "b1", "q", "b", "q-1", "q" + "9" * 12, "q" + "9" * 5000,
    "b" + "9" * 5000, "q٣", "q１", "r0", "\x00", "é", "\t",
]


def soup(tokens: list[str]) -> st.SearchStrategy[str]:
    return st.lists(st.sampled_from(tokens), max_size=40).map("".join) | st.lists(
        st.sampled_from(tokens), max_size=40).map(" ".join)


@st.composite
def circuits(draw) -> Circuit:
    width = draw(st.integers(1, 7))
    circuit = Circuit(width)
    for _ in range(draw(st.integers(0, 12))):
        size = draw(st.integers(1, min(width, 5)))
        wires = draw(st.permutations(range(width)))[:size]
        circuit.append({1: "x", 2: "cx", 3: "ccx"}.get(size, "mcx"), *wires)
    return circuit


def as_qasm2(circuit: Circuit) -> str:
    lines = ["OPENQASM 2.0;", 'include "qelib1.inc";', f"qreg q[{circuit.width}];"]
    lines += [f"{gate.name} " + ",".join(f"q[{q}]" for q in gate.qubits) + ";"
              for gate in circuit.gates]
    return "\n".join(lines) + "\n"


def as_qasm3(circuit: Circuit) -> str:
    lines = ["OPENQASM 3.0;", 'include "stdgates.inc";', f"qubit[{circuit.width}] q;"]
    for gate in circuit.gates:
        controls = len(gate.qubits) - 1
        modifier = "" if controls == 0 else "ctrl @ " if controls == 1 else f"ctrl({controls}) @ "
        lines.append(f"{modifier}x " + ", ".join(f"q[{q}]" for q in gate.qubits) + ";")
    return "\n".join(lines) + "\n"


INDEX_LITERALS = ["0", "1", "2", "3", "4", "5", "007", "9" * 12, "9" * 5000, "٣", "１", "-1",
                  " 2 ", ""]
"""In range, repeated, out of range, oversized, non-ASCII and malformed index spellings."""


@st.composite
def near_valid_qasm(draw) -> str:
    """Well-formed statements whose numbers and operand lists are often wrong.

    Blind mutation almost never produces a repeated or out-of-range operand inside an otherwise
    valid program; this strategy produces one in most examples.
    """
    version3 = draw(st.booleans())
    width = draw(st.sampled_from(["0", "1", "3", "4", "6", "004", "9" * 12, "9" * 5000, "٣"]))
    lines = (["OPENQASM 3.0;", 'include "stdgates.inc";', f"qubit[{width}] q;"] if version3
             else ["OPENQASM 2.0;", 'include "qelib1.inc";', f"qreg q[{width}];"])
    gates = ["x", "cx", "ccx", "mcx", "h"]
    modifiers = ["", "", "ctrl @ ", "ctrl(2) @ ", "ctrl(0) @ ", "ctrl(" + "9" * 5000 + ") @ "]
    for _ in range(draw(st.integers(0, 6))):
        operands = draw(st.lists(st.sampled_from(INDEX_LITERALS), min_size=1, max_size=5))
        modifier = draw(st.sampled_from(modifiers)) if version3 else ""
        lines.append(f"{modifier}{draw(st.sampled_from(gates))} "
                     + ",".join(f"q[{index}]" for index in operands) + ";")
    return "\n".join(lines) + "\n"


@st.composite
def near_valid_kmx(draw) -> str:
    lines = []
    for _ in range(draw(st.integers(0, 6))):
        name = draw(st.sampled_from(["X", "CX", "CCX", "SWAP", "CSWAP", "Z", "CZ", "CCZ", "HMR"]))
        operands = draw(st.lists(st.sampled_from(INDEX_LITERALS), min_size=1, max_size=4))
        line = f"{name} " + " ".join(f"q{index}" for index in operands)
        if name == "HMR":
            line = f"HMR q{operands[0]} b{draw(st.sampled_from(INDEX_LITERALS))}"
        elif draw(st.booleans()):
            line += f" if b{draw(st.sampled_from(INDEX_LITERALS))}"
        lines.append(line)
    return "\n".join(lines) + "\n"


def mutated(text: str, data) -> str:
    characters = list(text)
    for _ in range(data.draw(st.integers(1, 4))):
        position = data.draw(st.integers(0, len(characters)))
        action = data.draw(st.sampled_from(["insert", "delete", "duplicate"]))
        if action == "insert":
            characters[position:position] = list(data.draw(st.sampled_from(QASM_TOKENS)))
        elif action == "delete":
            del characters[position:position + data.draw(st.integers(1, 6))]
        else:
            source = data.draw(st.integers(0, len(characters)))
            characters[position:position] = characters[source:source + 12]
    return "".join(characters)


def assert_valid_circuit(circuit: object) -> None:
    assert type(circuit) is Circuit
    circuit.validate()
    assert 1 <= circuit.width <= MAX_INDEX


def check_qasm(text: str) -> None:
    try:
        circuit = parse_qasm(text)
    except REFUSALS as error:
        assert isinstance(error, SymqError) and isinstance(error, ValueError)
        assert str(error)
    else:
        assert_valid_circuit(circuit)


@SETTINGS
@given(st.text(max_size=200))
def test_qasm_arbitrary_text_is_parsed_or_refused(text):
    check_qasm(text)


@SETTINGS
@given(soup(QASM_TOKENS))
def test_qasm_token_soup_is_parsed_or_refused(text):
    check_qasm(text)


@SETTINGS
@given(circuits(), st.booleans(), st.data())
def test_a_mutated_valid_qasm_program_is_parsed_or_refused(circuit, version3, data):
    check_qasm(mutated(as_qasm3(circuit) if version3 else as_qasm2(circuit), data))


@SETTINGS
@given(near_valid_qasm())
def test_a_nearly_valid_qasm_program_is_parsed_or_refused(text):
    check_qasm(text)


@SETTINGS
@given(circuits())
def test_a_generated_circuit_survives_both_qasm_dialects(circuit):
    for text in (as_qasm2(circuit), as_qasm3(circuit)):
        parsed = parse_qasm(text)
        assert parsed.width == circuit.width
        assert parsed.gates == circuit.gates


COMMENT_TEXT = st.lists(st.sampled_from([
    "x q[0];", "cx q[0],q[1];", "//", "/*", ";", "qreg r[9];", "OPENQASM 2.0;", " ", "why",
    "ctrl @ x q[0], q[1];", "'", '"',
]), max_size=5).map(" ".join)


@st.composite
def commented(draw, text: str) -> str:
    """``text`` with comments added between its statements; the program it denotes is unchanged.

    The comment bodies contain statements, semicolons and the *other* kind of comment opener: a
    reader that strips comments wrongly either loses real statements or executes commented ones.
    """
    lines = []
    for line in text.splitlines():
        for _ in range(draw(st.integers(0, 2))):
            body = draw(COMMENT_TEXT)
            if draw(st.booleans()):
                lines.append("// " + body.replace("\n", " "))
            else:
                inner = body.replace("*/", "* /")
                if draw(st.booleans()):
                    inner = inner.replace(" ", "\n", 1)
                comment = f"/* {inner} */"
                # Before the header only whole-line comments keep the header first; elsewhere a
                # block comment may also share its line with the statement that follows.
                lines.append(comment if not lines or draw(st.booleans()) else comment + " ")
        lines.append(line)
    if draw(st.booleans()):
        lines.append("/* trailing // comment */")
    return "\n".join(lines) + "\n"


@SETTINGS
@given(circuits(), st.booleans(), st.data())
def test_comments_never_change_the_circuit(circuit, version3, data):
    """Found by review: ``//`` inside ``/* */`` used to swallow the statements that followed."""
    text = data.draw(commented(as_qasm3(circuit) if version3 else as_qasm2(circuit)))
    parsed = parse_qasm(text)
    assert parsed.width == circuit.width and parsed.gates == circuit.gates


@SETTINGS
@given(st.text(max_size=200) | soup(KMX_TOKENS) | near_valid_kmx())
def test_kmx_text_is_parsed_or_refused(text):
    try:
        program = parse_kmx(text)
    except REFUSALS as error:
        assert isinstance(error, SymqError) and str(error).startswith("line ")
    else:
        assert type(program) is KmxProgram
        for op in program.ops:
            assert all(type(q) is int and 0 <= q <= MAX_INDEX for q in op.qubits)


@st.composite
def near_valid_json_circuits(draw) -> bytes:
    """The right shape with wrong leaves: what an arbitrary JSON value almost never is."""
    junk = st.none() | st.booleans() | st.integers(-3, 9) | st.floats(allow_nan=False) | st.text(
        max_size=3) | st.lists(st.integers(0, 3), max_size=2)
    gates = draw(st.lists(st.tuples(
        st.sampled_from(["x", "cx", "ccx", "mcx", "h", ""]) | junk,
        st.lists(st.integers(0, 4) | junk, max_size=4) | junk), max_size=4))
    document = {"width": draw(st.integers(0, 5) | junk), "gates": [list(gate) for gate in gates]}
    if draw(st.booleans()):
        document["kind"] = draw(st.sampled_from(["classical_reversible", "other"]) | junk)
    return json.dumps(document).encode()


JSON_VALUES = st.recursive(
    st.none() | st.booleans() | st.integers(-5, 5) | st.floats(allow_nan=False) | st.text(
        max_size=5) | st.sampled_from(["x", "cx", "ccx", "mcx", "h", "width", "gates", "kind"]),
    lambda children: st.lists(children, max_size=4) | st.dictionaries(
        st.sampled_from(["width", "gates", "kind", "extra"]), children, max_size=4),
    max_leaves=20,
)


@SETTINGS
@given(st.sampled_from(["f.qasm", "f.kmx", "f.json", "f", "dir/f.QASM"]),
       st.binary(max_size=120) | soup(QASM_TOKENS + KMX_TOKENS).map(str.encode)
       | near_valid_qasm().map(str.encode) | near_valid_kmx().map(str.encode)
       | near_valid_json_circuits()
       | JSON_VALUES.map(lambda value: json.dumps(value).encode()))
def test_parse_circuit_returns_a_circuit_or_a_named_value_error(name, data):
    try:
        circuit = parse_circuit(data, name)
    except ValueError as error:
        assert str(error).startswith(f"{name}:")
    else:
        assert_valid_circuit(circuit)


# --- the leaks these properties found, as named regressions -------------------------------------

HEADER2 = 'OPENQASM 2.0;\ninclude "qelib1.inc";\n'


@pytest.mark.parametrize("body, fragment", [
    ("qreg q[2];\nx q[7];\n", "out of range"),                       # was a bare ValueError
    ("qreg q[2];\ncx q[0],q[0];\n", "repeated qubit"),               # was a bare ValueError
    ("qreg q[0];\n", "at least one qubit"),                          # was a bare ValueError
    ("qreg q[2];\nx q[" + "9" * 5000 + "];\n", "exceeds the supported maximum"),  # int() limit
    ("qreg q[" + "9" * 5000 + "];\n", "exceeds the supported maximum"),
    (f"qreg q[{MAX_INDEX + 1}];\n", "exceeds the supported maximum"),
    ("qreg q[2];\n// i " + "9" * 5000 + "\n", "exceeds the supported maximum"),
])
def test_a_malformed_qasm_number_or_operand_is_a_syntax_error(body, fragment):
    with pytest.raises(QasmSyntaxError, match=fragment):
        parse_qasm(HEADER2 + body)


def test_the_largest_supported_width_is_accepted_without_allocation():
    assert parse_qasm(HEADER2 + f"qreg q[{MAX_INDEX}];\nx q[{MAX_INDEX - 1}];\n").width == MAX_INDEX


@pytest.mark.parametrize("digit", ["٣", "１", "²"])
def test_only_ascii_digits_are_numbers(digit):
    """``\\d`` and ``int`` accept the decimal digits of every script; the grammar does not."""
    with pytest.raises(REFUSALS):
        parse_qasm(HEADER2 + f"qreg q[{digit}];\n")
    with pytest.raises(REFUSALS):
        parse_qasm(HEADER2 + f"qreg q[4];\nx q[{digit}];\n")
    with pytest.raises(REFUSALS):
        parse_kmx(f"X q{digit}\n")


def test_ctrl_zero_is_refused_instead_of_being_read_as_no_modifier():
    with pytest.raises(QasmSyntaxError, match=r"ctrl\(0\)"):
        parse_qasm("OPENQASM 3;\nqubit[2] q;\nctrl(0) @ x q[0];\n")
    with pytest.raises(QasmSyntaxError, match="control count exceeds"):
        parse_qasm("OPENQASM 3;\nqubit[2] q;\nctrl(" + "9" * 5000 + ") @ x q[0];\n")


@pytest.mark.parametrize("text, line", [
    (HEADER2 + "qreg q[2];\nx q[0];\nh q[1];\n", 5),
    (HEADER2 + "qreg q[2];\n/* a\n   block\n   comment */\nx q[5];\n", 7),
    (HEADER2 + "qreg q[2]; x q[0]; x q[9];\n", 3),
    (HEADER2 + "qreg q[2];\n\n\n   measure q[0];\n", 6),
    ("\n\nOPENQASM 2.0;\nOPENQASM 2.0;\n", 4),
])
def test_a_refused_statement_names_its_line(text, line):
    with pytest.raises(REFUSALS, match=rf"^line {line}: "):
        parse_qasm(text)


def test_parse_qasm_requires_text():
    with pytest.raises(TypeError):
        parse_qasm(b"OPENQASM 2.0;")


def test_a_file_that_is_not_utf8_is_a_syntax_error(tmp_path):
    (tmp_path / "bad.qasm").write_bytes(b"OPENQASM 2.0;\n\xff\xfe")
    (tmp_path / "bad.kmx").write_bytes(b"X q0\n\xff")
    with pytest.raises(QasmSyntaxError, match="not UTF-8"):
        load_qasm(tmp_path / "bad.qasm")
    with pytest.raises(KmxSyntaxError, match="not UTF-8"):
        load_kmx(tmp_path / "bad.kmx")


def test_an_oversized_kmx_index_is_a_syntax_error():
    with pytest.raises(KmxSyntaxError, match="line 2: qubit index exceeds"):
        parse_kmx("X q0\nX q" + "9" * 5000 + "\n")
    with pytest.raises(KmxSyntaxError, match="line 1: condition bit index exceeds"):
        parse_kmx("X q0 if b" + "9" * 5000 + "\n")
    assert parse_kmx(f"X q{MAX_INDEX}\n").ops[0].qubits == (MAX_INDEX,)
    assert parse_kmx("X q007\n").ops[0].qubits == (7,)


def test_deeply_nested_json_is_a_value_error_not_a_recursion_error():
    with pytest.raises(ValueError, match=r"^deep\.json: invalid JSON"):
        parse_circuit(b"[" * 100_000, "deep.json")


@pytest.mark.parametrize("digits, value", [
    ("0", 0), ("000", 0), ("007", 7), (str(MAX_INDEX), MAX_INDEX), ("0" * 5000 + "12", 12),
    (str(MAX_INDEX + 1), None), ("9" * 11, None), ("9" * 5000, None),
])
def test_the_shared_index_bound(digits, value):
    assert bounded_index(digits) == value


# --- defects found by an independent review of the readers --------------------------------------

def test_a_line_comment_opener_inside_a_block_comment_hides_nothing():
    """Two-pass stripping removed ``// not */ x q[1];`` first, then everything up to ``/* end */``.

    The file then parsed as a single ``x q[0]``: equal to a circuit it differs from, and
    different from the circuit it is. This defect predates the robustness work.
    """
    text = "OPENQASM 3;\nqubit[2] q;\nx q[0];\n/* why // not */ x q[1];\n/* end */\n"
    assert parse_qasm(text).gates == Circuit(2).x(0).x(1).gates
    assert parse_qasm("OPENQASM 3;\nqubit[2] q;\n// a /* b\nx q[0];\n// c */\n").gates \
        == Circuit(2).x(0).gates


@pytest.mark.parametrize("text, line", [("x q[0];\n/* never closed\nx q[1];\n", 4), ("/*/", 3)])
def test_an_unterminated_block_comment_is_a_syntax_error(text, line):
    with pytest.raises(QasmSyntaxError, match=rf"^line {line}: unterminated block comment"):
        parse_qasm(HEADER2 + text)


def test_many_unterminated_block_comments_are_refused_in_linear_time():
    """A regular expression retried the search from every ``/*``; the scanner looks once."""
    with pytest.raises(QasmSyntaxError, match="unterminated block comment"):
        parse_qasm(HEADER2 + "qreg q[2];\n" + "/* " * 200_000)


@pytest.mark.parametrize("annotation", ["// o 1 ٠", "// o ١ ٠", "// i １ ０", "// i 0 ١"])
def test_an_annotation_in_another_script_is_refused_not_skipped(annotation):
    """Regression of the ASCII-digit change: these stopped matching and became plain comments.

    A non-identity permutation annotation changes the meaning of the circuit, so skipping one
    is an acceptance of something that used to be refused.
    """
    with pytest.raises(QasmSyntaxError, match="ASCII decimal digits"):
        parse_qasm(HEADER2 + f"qreg q[2];\n{annotation}\nx q[0];\n")
    with pytest.raises(UnsupportedOperation, match="permutation"):
        parse_qasm(HEADER2 + "qreg q[2];\n// o 1 0\nx q[0];\n")
    assert parse_qasm(HEADER2 + "qreg q[2];\n// o 0 1\nx q[0];\n").gates == Circuit(2).x(0).gates


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_line_numbers_do_not_depend_on_the_line_ending(newline):
    text = newline.join(["OPENQASM 2.0;", 'include "qelib1.inc";', "qreg q[2];", "", "h q[0];", ""])
    with pytest.raises(UnsupportedOperation, match="^line 5: "):
        parse_qasm(text)
    valid = text.replace("h q[0];", "x q[0];")
    assert parse_qasm(valid).gates == Circuit(2).x(0).gates


@pytest.mark.parametrize("qubits", ["[null]", "[0.5]", "[true]", '["0"]', "[[0]]"])
def test_a_json_gate_with_non_integer_qubits_is_a_named_value_error(qubits):
    """``Gate`` raises ``TypeError`` for these; the loader's contract is a named ``ValueError``."""
    data = f'{{"width": 2, "gates": [["x", {qubits}]]}}'.encode()
    with pytest.raises(ValueError, match=r"^f\.json: ") as refusal:
        parse_circuit(data, "f.json")
    assert not isinstance(refusal.value, TypeError)
