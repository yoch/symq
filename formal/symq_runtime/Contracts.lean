import GateCNF
import PhaseBits
import AcyclicDAG
import GraphRewrites

/-!
  Independent statement contracts for the 54 theorems listed in
  tools/check_formal_axioms.py. The axiom checker pins theorem NAMES; this file
  pins their MEANING. Each contract restates the reviewed statement and is proved
  only by applying the original theorem, so weakening a statement, adding a
  hypothesis or changing a pinned definition makes `lake build` fail. A change
  to a statement must therefore be made here too, in plain sight of review.
  These are theorems about the abstract model, not about the Python runtime.
-/

namespace SymQContract
open SymQFormal

-- Definition pins. A theorem statement only means something relative to the
-- definitions it mentions, so every top-level definition of the four model files
-- is restated here and checked by `rfl` (equation by equation for recursive ones),
-- and the DAG constructors are restated with their argument types.
-- tools/check_formal_axioms.py requires every model `def` to appear in a pin.
-- Changing a definition breaks this file.

-- Type abbreviations.
example : Valuation = (Nat → Bool) := rfl
example : InputBits = (Nat → Bool) := rfl
example (n : Nat) : NodeBits n = (Fin n → Bool) := rfl

-- GateCNF: signed literals and the Tseitin AND/XOR clause lists.
example (v : Valuation) (l : Literal) :
    value v l = (if l.positive then v l.node else !(v l.node)) := rfl
example (v : Valuation) : clauseValue v [] = false := rfl
example (v : Valuation) (l : Literal) (ls : List Literal) :
    clauseValue v (l :: ls) = (value v l || clauseValue v ls) := rfl
example (v : Valuation) : cnfValue v [] = true := rfl
example (v : Valuation) (c : List Literal) (cs : List (List Literal)) :
    cnfValue v (c :: cs) = (clauseValue v c && cnfValue v cs) := rfl
example (z : Nat) (a b : Literal) :
    andCNF z a b = [[negative z, a], [negative z, b], [positive z, complement a, complement b]] := rfl
example (z : Nat) (a b : Literal) :
    xorCNF z a b = [[complement a, complement b, negative z], [a, b, negative z],
      [a, complement b, positive z], [complement a, b, positive z]] := rfl
example (gs : List Gate) : encode gs = gs.flatMap gateCNF := rfl
example (v : Valuation) (gs : List Gate) : graphMatches v gs = gs.all (gateMatches v) := rfl

-- PhaseBits: full adder and little-endian words.
example (b : Bool) : bit b = (if b then 1 else 0) := rfl
example (a b c : Bool) : sumBit a b c = ((a != b) != c) := rfl
example (a b c : Bool) : carryBit a b c = ((a && b) != ((a != b) && c)) := rfl

-- AcyclicDAG: evaluation, flat clauses and the runtime query shape.
example {n : Nat} (v : NodeBits n) (node : Fin n) (p : Bool) :
    signedRead v node p = (if p then v node else !(v node)) := rfl
example {n : Nat} (previous : DAG n) (key : Nat) (source : InputBits) :
    execute (.input previous key) source = extend (execute previous source) (source key) := rfl
example {n : Nat} (previous : DAG n) (a b : Fin n) (pa pb : Bool) (source : InputBits) :
    execute (.andGate previous a b pa pb) source =
      extend (execute previous source)
        (signedRead (execute previous source) a pa && signedRead (execute previous source) b pb) := rfl
example {n : Nat} (previous : DAG n) (a b : Fin n) (pa pb : Bool) (source : InputBits) :
    execute (.xorGate previous a b pa pb) source =
      extend (execute previous source)
        (signedRead (execute previous source) a pa != signedRead (execute previous source) b pb) := rfl
example (out a b : Bool) : andClauses out a b = (((!out || a) && (!out || b)) && (out || !a || !b)) := rfl
example (out a b : Bool) :
    xorClauses out a b = ((((!a || !b || !out) && (a || b || !out)) && (a || !b || out)) && (!a || b || out)) := rfl
example (v : InputBits) (l : FlatLiteral) :
    flatValue v l = (if l.polarity then v l.node else !(v l.node)) := rfl
example (v : InputBits) : flatCNFValue v [] = true := rfl
example (v : InputBits) (c : List FlatLiteral) (cs : List (List FlatLiteral)) :
    flatCNFValue v (c :: cs) = (flatClause v c && flatCNFValue v cs) := rfl
example (v : InputBits) : flatClause v [] = false := rfl
example (v : InputBits) (l : FlatLiteral) (ls : List FlatLiteral) :
    flatClause v (l :: ls) = (flatValue v l || flatClause v ls) := rfl
example (z : Nat) (a b : FlatLiteral) :
    flatAnd z a b = [[flatNegative z, a], [flatNegative z, b], [flatPositive z, flatNegate a, flatNegate b]] := rfl
example (z : Nat) (a b : FlatLiteral) :
    flatXor z a b = [[flatNegate a, flatNegate b, flatNegative z], [a, b, flatNegative z],
      [a, flatNegate b, flatPositive z], [flatNegate a, b, flatPositive z]] := rfl
example {n : Nat} (i : Fin n) (p : Bool) : flatChild i p = ⟨i.val + 2, p⟩ := rfl
example {n : Nat} (v : InputBits) (i : Fin n) : physicalNodeBits v i = v (i.val + 2) := rfl
example : runtimeGateClauses DAG.nil = [] := rfl
example {n : Nat} (previous : DAG n) (key : Nat) :
    runtimeGateClauses (.input previous key) = runtimeGateClauses previous := rfl
example {n : Nat} (previous : DAG n) (a b : Fin n) (pa pb : Bool) :
    runtimeGateClauses (.andGate previous a b pa pb) =
      runtimeGateClauses previous ++ flatAnd (n + 2) (flatChild a pa) (flatChild b pb) := rfl
example {n : Nat} (previous : DAG n) (a b : Fin n) (pa pb : Bool) :
    runtimeGateClauses (.xorGate previous a b pa pb) =
      runtimeGateClauses previous ++ flatXor (n + 2) (flatChild a pa) (flatChild b pb) := rfl
example {n : Nat} (dag : DAG n) (root : FlatLiteral) :
    runtimeQuery dag root = [[flatPositive 1]] ++ runtimeGateClauses dag ++ [[root]] := rfl

-- GraphRewrites.
example (a b : Bool) : xorBool a b = (a != b) := rfl

-- Further definition pins (audit #171, second review): every definition mentioned
-- by a listed statement is restated here, not only the UNSAT-soundness chain.
example (n : Nat) : positive n = ⟨n, true⟩ := rfl
example (n : Nat) : negative n = ⟨n, false⟩ := rfl
example (l : Literal) : complement l = ⟨l.node, !l.positive⟩ := rfl
example (n : Nat) : gateCNF (.input n) = [] := rfl
example (z : Nat) (a b : Literal) : gateCNF (.andGate z a b) = andCNF z a b := rfl
example (z : Nat) (a b : Literal) : gateCNF (.xorGate z a b) = xorCNF z a b := rfl
example (v : Valuation) (n : Nat) : gateMatches v (.input n) = true := rfl
example (v : Valuation) (z : Nat) (a b : Literal) :
    gateMatches v (.andGate z a b) = (v z == (value v a && value v b)) := rfl
example (v : Valuation) (z : Nat) (a b : Literal) :
    gateMatches v (.xorGate z a b) = (v z == (value v a != value v b)) := rfl
example : wordValue [] = 0 := rfl
example (b : Bool) (bs : List Bool) : wordValue (b :: bs) = bit b + 2 * wordValue bs := rfl
example (carry : Bool) : addWords [] [] carry = ([], carry) := rfl
example (a b carry : Bool) (as bs : List Bool) :
    addWords (a :: as) (b :: bs) carry =
      (sumBit a b carry :: (addWords as bs (carryBit a b carry)).1,
       (addWords as bs (carryBit a b carry)).2) := rfl

-- The DAG constructors, with their exact argument types.
example : DAG 0 := DAG.nil
example {n : Nat} (previous : DAG n) (key : Nat) : DAG (n + 1) := DAG.input previous key
example {n : Nat} (previous : DAG n) (a b : Fin n) (pa pb : Bool) : DAG (n + 1) :=
  DAG.andGate previous a b pa pb
example {n : Nat} (previous : DAG n) (a b : Fin n) (pa pb : Bool) : DAG (n + 1) :=
  DAG.xorGate previous a b pa pb
example {n : Nat} (v : NodeBits n) (bit : Bool) :
    extend v bit = fun i => if h : i.val < n then v ⟨i.val, h⟩ else bit := rfl
example {n : Nat} (v : NodeBits (n + 1)) : restrict v = fun i => v i.castSucc := rfl
example {n : Nat} (v : NodeBits (n + 1)) : finalBit v = v (Fin.last n) := rfl
example {n : Nat} (d : DAG n) : dagCount d = n := rfl
example : duplicateKeyDAG =
    DAG.xorGate (DAG.input (DAG.input DAG.nil 0) 0) ⟨0, by decide⟩ ⟨1, by decide⟩ true true := rfl
example (source : InputBits) (values : NodeBits 0) : satisfies DAG.nil source values = True := rfl
example {n : Nat} (previous : DAG n) (key : Nat) (source : InputBits) (values : NodeBits (n + 1)) :
    satisfies (.input previous key) source values =
      (satisfies previous source (restrict values) ∧ finalBit values = source key) := rfl
example {n : Nat} (previous : DAG n) (a b : Fin n) (pa pb : Bool) (source : InputBits)
    (values : NodeBits (n + 1)) :
    satisfies (.andGate previous a b pa pb) source values =
      (satisfies previous source (restrict values) ∧
        finalBit values = (signedRead (restrict values) a pa && signedRead (restrict values) b pb)) := rfl
example {n : Nat} (previous : DAG n) (a b : Fin n) (pa pb : Bool) (source : InputBits)
    (values : NodeBits (n + 1)) :
    satisfies (.xorGate previous a b pa pb) source values =
      (satisfies previous source (restrict values) ∧
        finalBit values = (signedRead (restrict values) a pa != signedRead (restrict values) b pb)) := rfl
example (source : InputBits) (values : NodeBits 0) : pinnedCNF DAG.nil source values = true := rfl
example {n : Nat} (previous : DAG n) (key : Nat) (source : InputBits) (values : NodeBits (n + 1)) :
    pinnedCNF (.input previous key) source values =
      (pinnedCNF previous source (restrict values) && (finalBit values == source key)) := rfl
example {n : Nat} (previous : DAG n) (a b : Fin n) (pa pb : Bool) (source : InputBits)
    (values : NodeBits (n + 1)) :
    pinnedCNF (.andGate previous a b pa pb) source values =
      (pinnedCNF previous source (restrict values) &&
        andClauses (finalBit values) (signedRead (restrict values) a pa)
          (signedRead (restrict values) b pb)) := rfl
example {n : Nat} (previous : DAG n) (a b : Fin n) (pa pb : Bool) (source : InputBits)
    (values : NodeBits (n + 1)) :
    pinnedCNF (.xorGate previous a b pa pb) source values =
      (pinnedCNF previous source (restrict values) &&
        xorClauses (finalBit values) (signedRead (restrict values) a pa)
          (signedRead (restrict values) b pb)) := rfl
example (node : Nat) : flatPositive node = ⟨node, true⟩ := rfl
example (node : Nat) : flatNegative node = ⟨node, false⟩ := rfl
example (l : FlatLiteral) : flatNegate l = ⟨l.node, !l.polarity⟩ := rfl
example (node : Nat) (expected : Bool) : flatPin node expected = [[⟨node, expected⟩]] := rfl
example (source : InputBits) : flatPinned DAG.nil source = [] := rfl
example {n : Nat} (previous : DAG n) (key : Nat) (source : InputBits) :
    flatPinned (.input previous key) source = flatPinned previous source ++ flatPin (n + 2) (source key) := rfl
example {n : Nat} (previous : DAG n) (a b : Fin n) (pa pb : Bool) (source : InputBits) :
    flatPinned (.andGate previous a b pa pb) source =
      flatPinned previous source ++ flatAnd (n + 2) (flatChild a pa) (flatChild b pb) := rfl
example {n : Nat} (previous : DAG n) (a b : Fin n) (pa pb : Bool) (source : InputBits) :
    flatPinned (.xorGate previous a b pa pb) source =
      flatPinned previous source ++ flatXor (n + 2) (flatChild a pa) (flatChild b pb) := rfl
example {n : Nat} (dag : DAG n) (source : InputBits) (root : FlatLiteral) :
    flatQuery dag source root = [[flatPositive 1]] ++ flatPinned dag source ++ [[root]] := rfl
example {n : Nat} (bits : NodeBits n) :
    physicalFromNodes bits = fun node =>
      if node = 1 then true
      else if h : 2 ≤ node ∧ node < n + 2 then bits ⟨node - 2, by omega⟩ else false := rfl
example (bits : NodeBits 0) : runtimeMatches DAG.nil bits = true := rfl
example {n : Nat} (previous : DAG n) (key : Nat) (bits : NodeBits (n + 1)) :
    runtimeMatches (.input previous key) bits = runtimeMatches previous (restrict bits) := rfl
example {n : Nat} (previous : DAG n) (a b : Fin n) (pa pb : Bool) (bits : NodeBits (n + 1)) :
    runtimeMatches (.andGate previous a b pa pb) bits =
      (runtimeMatches previous (restrict bits) &&
        andClauses (finalBit bits) (signedRead (restrict bits) a pa) (signedRead (restrict bits) b pb)) := rfl
example {n : Nat} (previous : DAG n) (a b : Fin n) (pa pb : Bool) (bits : NodeBits (n + 1)) :
    runtimeMatches (.xorGate previous a b pa pb) bits =
      (runtimeMatches previous (restrict bits) &&
        xorClauses (finalBit bits) (signedRead (restrict bits) a pa) (signedRead (restrict bits) b pb)) := rfl
example : inputKeys DAG.nil = [] := rfl
example {n : Nat} (previous : DAG n) (key : Nat) :
    inputKeys (.input previous key) = key :: inputKeys previous := rfl
example {n : Nat} (previous : DAG n) (a b : Fin n) (pa pb : Bool) :
    inputKeys (.andGate previous a b pa pb) = inputKeys previous := rfl
example {n : Nat} (previous : DAG n) (a b : Fin n) (pa pb : Bool) :
    inputKeys (.xorGate previous a b pa pb) = inputKeys previous := rfl
example : uniqueInputKeys DAG.nil = True := rfl
example {n : Nat} (previous : DAG n) (key : Nat) :
    uniqueInputKeys (.input previous key) = (uniqueInputKeys previous ∧ key ∉ inputKeys previous) := rfl
example {n : Nat} (previous : DAG n) (a b : Fin n) (pa pb : Bool) :
    uniqueInputKeys (.andGate previous a b pa pb) = uniqueInputKeys previous := rfl
example {n : Nat} (previous : DAG n) (a b : Fin n) (pa pb : Bool) :
    uniqueInputKeys (.xorGate previous a b pa pb) = uniqueInputKeys previous := rfl
example (source : InputBits) (bits : NodeBits 0) : inputMatches DAG.nil source bits = True := rfl
example {n : Nat} (previous : DAG n) (key : Nat) (source : InputBits) (bits : NodeBits (n + 1)) :
    inputMatches (.input previous key) source bits =
      (inputMatches previous source (restrict bits) ∧ finalBit bits = source key) := rfl
example {n : Nat} (previous : DAG n) (a b : Fin n) (pa pb : Bool) (source : InputBits) (bits : NodeBits (n + 1)) :
    inputMatches (.andGate previous a b pa pb) source bits = inputMatches previous source (restrict bits) := rfl
example {n : Nat} (previous : DAG n) (a b : Fin n) (pa pb : Bool) (source : InputBits) (bits : NodeBits (n + 1)) :
    inputMatches (.xorGate previous a b pa pb) source bits = inputMatches previous source (restrict bits) := rfl

-- Statements of GateCNF.lean.
theorem andCNF_exact_contract (v : Valuation) (z : Nat) (a b : Literal) : cnfValue v (andCNF z a b) = (v z == (value v a && value v b)) := by
  apply SymQFormal.andCNF_exact <;> assumption

theorem xorCNF_exact_contract (v : Valuation) (z : Nat) (a b : Literal) : cnfValue v (xorCNF z a b) = (v z == (value v a != value v b)) := by
  apply SymQFormal.xorCNF_exact <;> assumption

theorem encode_exact_contract (v : Valuation) (gs : List Gate) : cnfValue v (encode gs) = graphMatches v gs := by
  apply SymQFormal.encode_exact <;> assumption

theorem unsat_excludes_gate_counterexample_contract (gs : List Gate) (root : Literal) (hunsat : ∀ v : Valuation, cnfValue v (encode gs ++ [[root]]) = false) (v : Valuation) (hok : graphMatches v gs = true) : value v root = false := by
  apply SymQFormal.unsat_excludes_gate_counterexample <;> assumption

-- Statements of PhaseBits.lean.
theorem fullAdder_exact_contract (a b carry : Bool) : bit (sumBit a b carry) + 2 * bit (carryBit a b carry) = bit a + bit b + bit carry := by
  apply SymQFormal.fullAdder_exact <;> assumption

theorem addWords_exact_contract (xs ys : List Bool) (carry : Bool) (h : xs.length = ys.length) : wordValue (addWords xs ys carry).1 + 2 ^ xs.length * bit (addWords xs ys carry).2 = wordValue xs + wordValue ys + bit carry := by
  apply SymQFormal.addWords_exact <;> assumption

-- Statements of AcyclicDAG.lean.
theorem restrict_extend_contract (v : NodeBits n) (bit : Bool) : restrict (extend v bit) = v := by
  apply SymQFormal.restrict_extend <;> assumption

theorem finalBit_extend_contract (v : NodeBits n) (bit : Bool) : finalBit (extend v bit) = bit := by
  apply SymQFormal.finalBit_extend <;> assumption

theorem extend_restrict_final_contract (v : NodeBits (n+1)) : extend (restrict v) (finalBit v) = v := by
  apply SymQFormal.extend_restrict_final <;> assumption

theorem execute_satisfies_contract {n : Nat} (dag : DAG n) (source : InputBits) : satisfies dag source (execute dag source) := by
  apply SymQFormal.execute_satisfies <;> assumption

theorem satisfies_unique_contract {n : Nat} (dag : DAG n) (source : InputBits) (values : NodeBits n) (h : satisfies dag source values) : values = execute dag source := by
  apply SymQFormal.satisfies_unique <;> assumption

theorem unique_model_contract {n : Nat} (dag : DAG n) (source : InputBits) : ∃ values : NodeBits n, satisfies dag source values ∧ ∀ other : NodeBits n, satisfies dag source other → other = values := by
  apply SymQFormal.unique_model <;> assumption

theorem andClauses_exact_contract (out a b : Bool) : andClauses out a b = (out == (a && b)) := by
  apply SymQFormal.andClauses_exact <;> assumption

theorem xorClauses_exact_contract (out a b : Bool) : xorClauses out a b = (out == (a != b)) := by
  apply SymQFormal.xorClauses_exact <;> assumption

theorem pinnedCNF_exact_contract {n : Nat} (dag : DAG n) (source : InputBits) (values : NodeBits n) : pinnedCNF dag source values = true ↔ satisfies dag source values := by
  apply SymQFormal.pinnedCNF_exact <;> assumption

theorem pinnedCNF_unique_model_contract {n : Nat} (dag : DAG n) (source : InputBits) : ∃ values : NodeBits n, pinnedCNF dag source values = true ∧ ∀ other : NodeBits n, pinnedCNF dag source other = true → other = values := by
  apply SymQFormal.pinnedCNF_unique_model <;> assumption

theorem pinnedCNF_root_unsat_contract {n : Nat} (dag : DAG n) (source : InputBits) (root : Fin n) (hunsat : ∀ values : NodeBits n, pinnedCNF dag source values = true → values root = false) : (execute dag source) root = false := by
  apply SymQFormal.pinnedCNF_root_unsat <;> assumption

theorem flatAnd_exact_contract (v : InputBits) (z : Nat) (a b : FlatLiteral) : flatCNFValue v (flatAnd z a b) = andClauses (v z) (flatValue v a) (flatValue v b) := by
  apply SymQFormal.flatAnd_exact <;> assumption

theorem flatXor_exact_contract (v : InputBits) (z : Nat) (a b : FlatLiteral) : flatCNFValue v (flatXor z a b) = xorClauses (v z) (flatValue v a) (flatValue v b) := by
  apply SymQFormal.flatXor_exact <;> assumption

theorem flatPin_exact_contract (v : InputBits) (node : Nat) (expected : Bool) : flatCNFValue v (flatPin node expected) = (v node == expected) := by
  apply SymQFormal.flatPin_exact <;> assumption

theorem flatPinned_exact_contract (v source : InputBits) {n : Nat} (dag : DAG n) : flatCNFValue v (flatPinned dag source) = pinnedCNF dag source (physicalNodeBits v) := by
  apply SymQFormal.flatPinned_exact <;> assumption

theorem flatQuery_exact_contract (v source : InputBits) (dag : DAG n) (root : FlatLiteral) : flatCNFValue v (flatQuery dag source root) = (v 1 && pinnedCNF dag source (physicalNodeBits v) && flatValue v root) := by
  apply SymQFormal.flatQuery_exact <;> assumption

theorem physicalFromNodes_one_contract {n : Nat} (bits : NodeBits n) : physicalFromNodes bits 1 = true := by
  apply SymQFormal.physicalFromNodes_one <;> assumption

theorem physicalFromNodes_read_contract {n : Nat} (bits : NodeBits n) : physicalNodeBits (physicalFromNodes bits) = bits := by
  apply SymQFormal.physicalFromNodes_read <;> assumption

theorem flatQuery_sat_iff_contract (dag : DAG n) (source : InputBits) (node : Fin n) (polarity : Bool) : (∃ physical : InputBits, flatCNFValue physical (flatQuery dag source (flatChild node polarity)) = true) ↔ signedRead (execute dag source) node polarity = true := by
  apply SymQFormal.flatQuery_sat_iff <;> assumption

theorem flatQuery_unsat_iff_contract (dag : DAG n) (source : InputBits) (node : Fin n) (polarity : Bool) : (∀ physical : InputBits, flatCNFValue physical (flatQuery dag source (flatChild node polarity)) = false) ↔ signedRead (execute dag source) node polarity = false := by
  apply SymQFormal.flatQuery_unsat_iff <;> assumption

theorem runtimeGateClauses_exact_contract (v : InputBits) (dag : DAG n) : flatCNFValue v (runtimeGateClauses dag) = runtimeMatches dag (physicalNodeBits v) := by
  apply SymQFormal.runtimeGateClauses_exact <;> assumption

theorem runtimeMatches_of_satisfies_contract (dag : DAG n) (source : InputBits) (bits : NodeBits n) (h : satisfies dag source bits) : runtimeMatches dag bits = true := by
  apply SymQFormal.runtimeMatches_of_satisfies <;> assumption

theorem runtimeQuery_exact_contract (v : InputBits) (dag : DAG n) (root : FlatLiteral) : flatCNFValue v (runtimeQuery dag root) = (v 1 && runtimeMatches dag (physicalNodeBits v) && flatValue v root) := by
  apply SymQFormal.runtimeQuery_exact <;> assumption

theorem runtimeQuery_unsat_sound_contract (dag : DAG n) (node : Fin n) (polarity : Bool) (hunsat : ∀ physical : InputBits, flatCNFValue physical (runtimeQuery dag (flatChild node polarity)) = false) (source : InputBits) : signedRead (execute dag source) node polarity = false := by
  apply SymQFormal.runtimeQuery_unsat_sound <;> assumption

theorem duplicateKeySourceAlwaysZero_contract (source : InputBits) : signedRead (execute duplicateKeyDAG source) ⟨2, by decide⟩ true = false := by
  apply SymQFormal.duplicateKeySourceAlwaysZero <;> assumption

theorem duplicateKeyUnpinnedSAT_contract : ∃ physical : InputBits, flatCNFValue physical (runtimeQuery duplicateKeyDAG (flatChild (⟨2, by decide⟩ : Fin 3) true)) = true := by
  apply SymQFormal.duplicateKeyUnpinnedSAT <;> assumption

theorem inputMatches_congr_contract (dag : DAG n) : ∀ (s t : InputBits) (bits : NodeBits n), (∀ key, key ∈ inputKeys dag → s key = t key) → inputMatches dag s bits → inputMatches dag t bits := by
  apply SymQFormal.inputMatches_congr <;> assumption

theorem source_exists_unique_keys_contract (dag : DAG n) : ∀ bits : NodeBits n, uniqueInputKeys dag → ∃ source : InputBits, inputMatches dag source bits := by
  apply SymQFormal.source_exists_unique_keys <;> assumption

theorem runtimeMatches_inputMatches_contract (dag : DAG n) : ∀ (source : InputBits) (bits : NodeBits n), runtimeMatches dag bits = true → inputMatches dag source bits → satisfies dag source bits := by
  apply SymQFormal.runtimeMatches_inputMatches <;> assumption

theorem runtimeQuery_sat_complete_unique_keys_contract (dag : DAG n) (hunique : uniqueInputKeys dag) (node : Fin n) (polarity : Bool) : (∃ physical : InputBits, flatCNFValue physical (runtimeQuery dag (flatChild node polarity)) = true) → (∃ source : InputBits, signedRead (execute dag source) node polarity = true) := by
  apply SymQFormal.runtimeQuery_sat_complete_unique_keys <;> assumption

theorem runtimeQuery_sat_iff_unique_keys_contract (dag : DAG n) (hunique : uniqueInputKeys dag) (node : Fin n) (polarity : Bool) : (∃ physical : InputBits, flatCNFValue physical (runtimeQuery dag (flatChild node polarity)) = true) ↔ (∃ source : InputBits, signedRead (execute dag source) node polarity = true) := by
  apply SymQFormal.runtimeQuery_sat_iff_unique_keys <;> assumption

theorem runtimeQuery_unsat_iff_unique_keys_contract (dag : DAG n) (hunique : uniqueInputKeys dag) (node : Fin n) (polarity : Bool) : (∀ physical : InputBits, flatCNFValue physical (runtimeQuery dag (flatChild node polarity)) = false) ↔ (∀ source : InputBits, signedRead (execute dag source) node polarity = false) := by
  apply SymQFormal.runtimeQuery_unsat_iff_unique_keys <;> assumption

theorem uniqueInputKeys_iff_nodup_contract (dag : DAG n) : uniqueInputKeys dag ↔ (inputKeys dag).Nodup := by
  apply SymQFormal.uniqueInputKeys_iff_nodup <;> assumption

-- Statements of GraphRewrites.lean.
theorem xor_commutative_contract (a b : Bool) : xorBool a b = xorBool b a := by
  apply SymQFormal.xor_commutative <;> assumption

theorem xor_zero_contract (a : Bool) : xorBool a false = a := by
  apply SymQFormal.xor_zero <;> assumption

theorem xor_one_contract (a : Bool) : xorBool a true = !a := by
  apply SymQFormal.xor_one <;> assumption

theorem xor_self_contract (a : Bool) : xorBool a a = false := by
  apply SymQFormal.xor_self <;> assumption

theorem xor_complement_contract (a : Bool) : xorBool a (!a) = true := by
  apply SymQFormal.xor_complement <;> assumption

theorem xor_cancel_left_contract (a b : Bool) : xorBool (xorBool a b) a = b := by
  apply SymQFormal.xor_cancel_left <;> assumption

theorem xor_cancel_right_contract (a b : Bool) : xorBool (xorBool a b) b = a := by
  apply SymQFormal.xor_cancel_right <;> assumption

theorem xor_signed_left_contract (a b : Bool) : xorBool (!a) b = !(xorBool a b) := by
  apply SymQFormal.xor_signed_left <;> assumption

theorem xor_signed_right_contract (a b : Bool) : xorBool a (!b) = !(xorBool a b) := by
  apply SymQFormal.xor_signed_right <;> assumption

theorem xor_signed_both_contract (a b : Bool) : xorBool (!a) (!b) = xorBool a b := by
  apply SymQFormal.xor_signed_both <;> assumption

theorem and_commutative_contract (a b : Bool) : (a && b) = (b && a) := by
  apply SymQFormal.and_commutative <;> assumption

theorem and_zero_contract (a : Bool) : (a && false) = false := by
  apply SymQFormal.and_zero <;> assumption

theorem and_one_contract (a : Bool) : (a && true) = a := by
  apply SymQFormal.and_one <;> assumption

theorem and_self_contract (a : Bool) : (a && a) = a := by
  apply SymQFormal.and_self <;> assumption

theorem and_complement_contract (a : Bool) : (a && !a) = false := by
  apply SymQFormal.and_complement <;> assumption

end SymQContract
