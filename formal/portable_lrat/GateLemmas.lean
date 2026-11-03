import Std

/- First formally checked reduction lemmas, NOT a proof of the Python encoder.
   Each Boolean gate theorem covers all valuations, including complemented edges
   through the Boolean input values. No external computation oracle is used. -/
namespace SymQPortable

def andClauses (a b z : Bool) : Bool :=
  ((!z || a) && (!z || b)) && (z || !a || !b)

theorem andClauses_iff (a b z : Bool) :
    andClauses a b z = true ↔ z = (a && b) := by
  cases a <;> cases b <;> cases z <;> decide

def xorClauses (a b z : Bool) : Bool :=
  (((!a || !b || !z) && (a || b || !z)) && (a || !b || z)) && (!a || b || z)

theorem xorClauses_iff (a b z : Bool) :
    xorClauses a b z = true ↔ z = (a != b) := by
  cases a <;> cases b <;> cases z <;> decide

/-- A checked aggregate candidate is constant on each signature fibre of the
    declared domain. This logical lemma does not prove that Python extracted
    the correct signature, phase delta or quantum semantics. -/
theorem fibre_constancy {X H R : Type} (domain : X → Prop)
    (signature : X → H) (delta : X → R) (candidate : H → R)
    (bound : ∀ x, domain x → delta x = candidate (signature x))
    (x y : X) (hx : domain x) (hy : domain y)
    (same : signature x = signature y) : delta x = delta y := by
  rw [bound x hx, bound y hy, same]

#print axioms andClauses_iff
#print axioms xorClauses_iff
#print axioms fibre_constancy
end SymQPortable
