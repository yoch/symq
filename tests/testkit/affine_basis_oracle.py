"""Exact all-matrix-unit reference, independent of ANF, kernels and modular lifts."""
from __future__ import annotations

from fractions import Fraction

from symq.phase_oracle import run_program

_ANGLES = {"t": Fraction(1, 8), "tdg": Fraction(-1, 8), "s": Fraction(1, 4),
           "sdg": Fraction(-1, 4), "z": Fraction(1, 2), "cz": Fraction(1, 2),
           "ccz": Fraction(1, 2)}


def scalar(program, assignment, k):
    state, phase = assignment, 0
    for gate in program.gates:
        if gate.name in ("x", "cx", "ccx", "mcx"):
            if all((state // (2**q)) % 2 for q in gate.wires[:-1]):
                state ^= 2**gate.wires[-1]
        elif all((state // (2**q)) % 2 for q in gate.wires):
            angle = gate.angle if gate.name == "phase" else _ANGLES[gate.name]
            exponent = Fraction(angle) * 2**k
            assert exponent.denominator == 1
            phase += exponent.numerator
    return state, phase % 2**k


class ExactChannel:
    def __init__(self, case, *, points=None):
        if points is None and len(case.support.columns) > 8 or case.dephaser.measurements > 6:
            raise ValueError("small reference domain only")
        self.case = case
        self.k = max(case.left.k, case.right.k)
        self.points = []
        if points is None:
            for z in range(2**len(case.support.columns)):
                point = case.support.offset
                for j, column in enumerate(case.support.columns):
                    if z // 2**j % 2:
                        point ^= column
                self.points.append(point)
        else:
            pivots = {}
            for column in case.support.columns:
                reduced = column
                while reduced:
                    position = reduced.bit_length() - 1
                    if position not in pivots:
                        pivots[position] = reduced
                        break
                    reduced ^= pivots[position]
            for point in dict.fromkeys(points):
                if type(point) is not int or not 0 <= point < 2**case.support.width:
                    raise ValueError("witness point outside ambient width")
                reduced = point ^ case.support.offset
                while reduced:
                    position = reduced.bit_length() - 1
                    if position not in pivots:
                        raise ValueError("witness point outside declared support")
                    reduced ^= pivots[position]
                self.points.append(point)
        assert len(set(self.points)) == len(self.points)
        self.branches = {(x, m): run_program(case.dephaser, x, m)
                         for x in self.points for m in range(2**case.dephaser.measurements)}
        data_mask = 2**case.dephaser.data - 1
        all_outputs = {output for branch in self.branches.values() for output in branch}
        self.images = {}
        for side, program in enumerate((case.left, case.right)):
            for output in all_outputs:
                image, phase = scalar(program, output & data_mask, self.k)
                self.images[side, output] = (image | (output & ~data_mask), phase)

    def unit(self, side, x, y):
        total, half, modulus = {}, 2**(self.k - 1), 2**self.k
        for outcome in range(2**self.case.dephaser.measurements):
            for ox, ax in self.branches[x, outcome].items():
                for oy, ay in self.branches[y, outcome].items():
                    image_x, phase_x = self.images[side, ox]
                    image_y, phase_y = self.images[side, oy]
                    exponent, coefficient = (phase_x - phase_y) % modulus, ax * ay
                    if exponent >= half:
                        exponent -= half
                        coefficient = -coefficient
                    key = image_x, image_y, exponent
                    total[key] = total.get(key, 0) + coefficient
                    if not total[key]:
                        del total[key]
        return total

    def compare(self):
        first_difference, compared = None, 0
        for x in self.points:
            for y in self.points:
                compared += 1
                if self.unit(0, x, y) != self.unit(1, x, y) and first_difference is None:
                    first_difference = x, y
        return {"equivalent": first_difference is None, "coherences": compared,
                "first_difference": first_difference}

    def validates_witness(self, witness):
        x, y = witness
        return x in self.points and y in self.points and self.unit(0, x, y) != self.unit(1, x, y)
