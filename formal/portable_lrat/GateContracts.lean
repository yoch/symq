import GateLemmas

/-!
  Statement contracts for the three hand-written gate lemmas (audit #171).
  The qualification pins theorem names and axioms; this file pins meaning.
  Each definition is restated by `rfl` and each statement is proved only by
  applying the original lemma, so a weakened statement or a changed clause
  definition makes `lake build` fail. The clause lists are those emitted by
  `phase_proof_bundle._encode_graph`: AND [-z,a] [-z,b] [z,-a,-b] and XOR
  [-a,-b,-z] [a,b,-z] [a,-b,z] [-a,b,z].
-/

namespace SymQPortableContract
open SymQPortable

example (a b z : Bool) :
    andClauses a b z = (((!z || a) && (!z || b)) && (z || !a || !b)) := rfl

example (a b z : Bool) :
    xorClauses a b z =
      ((((!a || !b || !z) && (a || b || !z)) && (a || !b || z)) && (!a || b || z)) := rfl

theorem andClauses_iff_contract (a b z : Bool) :
    andClauses a b z = true ↔ z = (a && b) := by
  apply SymQPortable.andClauses_iff <;> assumption

theorem xorClauses_iff_contract (a b z : Bool) :
    xorClauses a b z = true ↔ z = (a != b) := by
  apply SymQPortable.xorClauses_iff <;> assumption

theorem fibre_constancy_contract {X H R : Type} (domain : X → Prop)
    (signature : X → H) (delta : X → R) (candidate : H → R)
    (bound : ∀ x, domain x → delta x = candidate (signature x))
    (x y : X) (hx : domain x) (hy : domain y)
    (same : signature x = signature y) : delta x = delta y := by
  apply SymQPortable.fibre_constancy <;> assumption

end SymQPortableContract
