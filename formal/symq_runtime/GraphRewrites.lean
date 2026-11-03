import Std

/-!
  Universal Boolean algebra used by Graph.xor/Graph.mul shortcuts. Theorems
  cover all valuations, not samples. The Python optimizer implementation
  remains a separately tested refinement obligation.
-/
namespace SymQFormal

def xorBool (a b : Bool) : Bool := a != b

theorem xor_commutative (a b : Bool) :
    xorBool a b = xorBool b a := by
  cases a <;> cases b <;> decide

theorem xor_zero (a : Bool) : xorBool a false = a := by
  cases a <;> decide

theorem xor_one (a : Bool) : xorBool a true = !a := by
  cases a <;> decide

theorem xor_self (a : Bool) : xorBool a a = false := by
  cases a <;> decide

theorem xor_complement (a : Bool) : xorBool a (!a) = true := by
  cases a <;> decide

theorem xor_cancel_left (a b : Bool) :
    xorBool (xorBool a b) a = b := by
  cases a <;> cases b <;> decide

theorem xor_cancel_right (a b : Bool) :
    xorBool (xorBool a b) b = a := by
  cases a <;> cases b <;> decide

theorem xor_signed_left (a b : Bool) :
    xorBool (!a) b = !(xorBool a b) := by
  cases a <;> cases b <;> decide

theorem xor_signed_right (a b : Bool) :
    xorBool a (!b) = !(xorBool a b) := by
  cases a <;> cases b <;> decide

theorem xor_signed_both (a b : Bool) :
    xorBool (!a) (!b) = xorBool a b := by
  cases a <;> cases b <;> decide

theorem and_commutative (a b : Bool) : (a && b) = (b && a) := by
  cases a <;> cases b <;> decide

theorem and_zero (a : Bool) : (a && false) = false := by
  cases a <;> decide

theorem and_one (a : Bool) : (a && true) = a := by
  cases a <;> decide

theorem and_self (a : Bool) : (a && a) = a := by
  cases a <;> decide

theorem and_complement (a : Bool) : (a && !a) = false := by
  cases a <;> decide

#print axioms xor_commutative
#print axioms xor_zero
#print axioms xor_one
#print axioms xor_self
#print axioms xor_complement
#print axioms xor_cancel_left
#print axioms xor_cancel_right
#print axioms xor_signed_left
#print axioms xor_signed_right
#print axioms xor_signed_both
#print axioms and_commutative
#print axioms and_zero
#print axioms and_one
#print axioms and_self
#print axioms and_complement

end SymQFormal
