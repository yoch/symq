import Std

/-!
  Exact Boolean ripple-carry accounting for phase addition modulo 2^k.
  This is the arithmetic model used by the bit-sliced phase accumulator.
  It does not claim the Python code is mechanically refined to this model.
-/
namespace SymQFormal

def bit (b : Bool) : Nat := if b then 1 else 0

def sumBit (a b carry : Bool) : Bool := (a != b) != carry

def carryBit (a b carry : Bool) : Bool :=
  (a && b) != ((a != b) && carry)

theorem fullAdder_exact (a b carry : Bool) :
    bit (sumBit a b carry) + 2 * bit (carryBit a b carry) =
      bit a + bit b + bit carry := by
  cases a <;> cases b <;> cases carry <;> decide

def wordValue : List Bool → Nat
  | [] => 0
  | b :: bs => bit b + 2 * wordValue bs

/-- Little-endian k-bit addition. The final carry is deliberately retained here
    to state the stronger exact theorem, rather than assuming modular arithmetic. -/
def addWords : List Bool → List Bool → Bool → (List Bool × Bool)
  | [], [], carry => ([], carry)
  | a :: as, b :: bs, carry =>
      let next := carryBit a b carry
      let rest := addWords as bs next
      (sumBit a b carry :: rest.1, rest.2)
  | _, _, carry => ([], carry)

theorem addWords_exact (xs ys : List Bool) (carry : Bool)
    (h : xs.length = ys.length) :
    wordValue (addWords xs ys carry).1 +
      2 ^ xs.length * bit (addWords xs ys carry).2 =
        wordValue xs + wordValue ys + bit carry := by
  induction xs generalizing ys carry with
  | nil =>
      cases ys with
      | nil => simp [addWords, wordValue]
      | cons y ys => simp at h
  | cons a xs ih =>
      cases ys with
      | nil => simp at h
      | cons b ys =>
          have hlen : xs.length = ys.length := by simpa using h
          have hrec := ih ys (carryBit a b carry) hlen
          have hfull := fullAdder_exact a b carry
          change bit (sumBit a b carry) + 2 * wordValue (addWords xs ys (carryBit a b carry)).1 +
                2 ^ (xs.length + 1) * bit (addWords xs ys (carryBit a b carry)).2 =
                bit a + 2 * wordValue xs + (bit b + 2 * wordValue ys) + bit carry
          calc
            bit (sumBit a b carry) + 2 * wordValue (addWords xs ys (carryBit a b carry)).1 +
                2 ^ (xs.length + 1) * bit (addWords xs ys (carryBit a b carry)).2
              = bit (sumBit a b carry) +
                  2 * (wordValue (addWords xs ys (carryBit a b carry)).1 +
                    2 ^ xs.length * bit (addWords xs ys (carryBit a b carry)).2) := by
                    simp [pow_succ, Nat.mul_add, Nat.mul_assoc, Nat.add_assoc]
            _ = bit (sumBit a b carry) +
                  2 * (wordValue xs + wordValue ys + bit (carryBit a b carry)) := by
                    rw [hrec]
            _ = bit a + 2 * wordValue xs + (bit b + 2 * wordValue ys) + bit carry := by
                    omega

#print axioms fullAdder_exact
#print axioms addWords_exact
end SymQFormal
