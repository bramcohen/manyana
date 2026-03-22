# Manyana

A fundamentally sound basis for a version control system. Built on CRDTs, it provides eventual consistency — merges never fail and always converge to the same result — with conflict presentations which are much more informative and helpful than the norm.

## Why CRDTs for Version Control

CRDTs (Conflict-Free Replicated Data Types) are long overdue as a fundamentally sound basis for version control. They give you commutativity and associativity of merges for free — properties which traditional VCS systems have to approximate with heuristics and which break down in painful ways during complex merge histories.

The hold-up has been twofold. First, CRDTs are an obscure data structure from the distributed systems world and version control is its own deep domain — the crossover between the two has been underexplored. Second, and harder, is the UX. A CRDT is by definition *conflict-free* — every merge produces a deterministic result — so what does it even mean to show conflicts? This project works out those UX problems.

This algorithm is deeply history-aware — but the broader field of version control has quietly, implicitly accepted that version control *should* be history-aware already. Not just in the sense of tracking history, but in using history to resolve conflicts in ways more involved than simply smashing two sides together given a single common ancestor. Git does this with either subtle history traversal when there isn't a single latest common ancestor (relatively new behavior) or with rebase, which was always extremely history-aware. CRDTs just make the whole thing principled.

## Conflicts in a Conflict-Free World

The merge algorithm always produces a result. There is no failure case. But "conflict-free" doesn't mean "no conflicts worth showing to the user." The heuristic is that a conflict happens when concurrent edits are *too near* each other — close enough in the document structure that a human should review the combined result rather than having it silently auto-merged. Specifically, "near" means immediately adjacent or only separated by whitespace lines. This is of course a heuristic that can be iterated on.

Consider a concrete example. Two people branch from a file containing:

```
def calculate(x):
    a = x * 2
    b = a + 1
    return b
```

Left deletes the entire function. Right adds a logging line in the middle:

```
def calculate(x):
    a = x * 2
    logger.debug(f"a={a}")
    b = a + 1
    return b
```

A traditional VCS gives you something like this:

```
<<<<<<< left
=======
def calculate(x):
    a = x * 2
    logger.debug(f"a={a}")
    b = a + 1
    return b
>>>>>>> right
```

Two opaque blobs. You can see that one side has nothing and the other has code, but you have to mentally reconstruct what actually happened.

Manyana's output tells you *what each side did*:

```
<<<<<<< begin deleted left
def calculate(x):
    a = x * 2
======= begin added right
    logger.debug(f"a={a}")
======= begin deleted left
    b = a + 1
    return b
>>>>>>> end conflict
```

Now you can see the structure of the conflict: left deleted the function, and right inserted a line into the middle of it. Each section is labeled with the action and which side performed it. This is both more informative and more honest about what happened — it doesn't force the conflict into a binary "ours vs. theirs" frame.

This kind of scenario — deletion on one side, insertion on the other — is one of the trickiest UX problems for applying CRDTs to text. A naive CRDT would silently keep the inserted line floating in space after the surrounding function was deleted. Manyana instead surfaces it as a conflict, because the edits were *too near* each other to auto-resolve without human judgment.

## Properties

- **Git-style workflow** — The high-level API follows the familiar git flow of commits and merges. You commit new file contents with `update_state` and combine branches with `merge_states`.
- **Commutative merges** — `merge(A, B)` produces the same result as `merge(B, A)`, making it suitable for decentralized workflows where there is no canonical ordering of branches.
- **No interleaving** — If two branches independently insert code at the same point, the merge will never interleave lines from both sides. It will always place one block then the other. This is a structural guarantee from the CRDT, not a heuristic.
- **History-aware state** — The state captures enough about a file's edit history to correctly merge with any other branch which shares a common ancestor, without needing access to the original commits.
- **Linear complexity** — The state size is linear on the number of lines that have *ever* been in the file, and performing a merge over two states is a single linear pass.
- **Structurally determined** — The algorithm is completely structural: if two different branches undergo the exact same patches in the exact same order, they will have literally identical states. Same inputs, same history. But this also means the diff algorithm matters — the exact interpretation of what happened in a diff gets baked in at commit time. Two different diff algorithms applied to the same edit could produce different states, which would merge correctly with each other but would carry different structural records of how the edit happened.

## Why Line Ordering Has to Be Universal

Having a universal permanent ordering of lines is a limitation of weaves, but it's also a hard requirement of the eventual consistency property. Eventual consistency means that if multiple branches are merged together, no matter what order they're merged in, the result will be exactly the same. This is the property which makes decentralized workflows actually work.

To see why universal ordering matters, consider what happens without it. Say `AB` is branched, and one branch changes it to `AXB` while the other changes it to `AYB`. Both X and Y belong in the final result, and the merge is flagged as a conflict. Two different people resolve this conflict on two different branches. One resolves it to `AXYB`, the other to `AYXB`. Now you have to merge *those* two versions together — and every option is bad:

- Clean merge to `AXB` or `AYB` — obviously wrong, silently drops someone's code. Some systems in the wild do this.
- Clean merge to `AXYXB` or `AYXYB` — also wrong, duplicates lines. Some systems in the wild also do this.
- Present it as a conflict `A` `<<<` `XY` `===` `YX` `>>>` `B` — arguably the least bad option, but it becomes impossible to make reliable in even slightly more complex cases. Worse, it implies that clean merging to `AXYYXB` is a reasonable resolution, which it most definitely is not. And if you're ordering local then remote, each branch might resolve the conflict to their own local version by default — resulting in them getting literally the same conflict regenerated on every merge until the end of time.

Git's policy of presenting merge conflicts with local followed by remote is just asking for this kind of ordering pain. The right way to fix the problem is to never get into that position in the first place. When the CRDT decides that X comes before Y (or Y before X), that ordering is baked into the structure permanently and every future merge respects it. Two people resolving the same conflict independently will always produce the same result, because the ordering was never theirs to choose.

## API

Four functions make up the public interface:

### `initial_state(lines) → state_string`

Creates a new state from a list of lines. This is the starting point for tracking a file.

```python
state = initial_state(['hello', 'world'])
```

### `current_lines(state_string) → [line]`

Reconstructs the current visible lines from a state.

```python
lines = current_lines(state)  # ['hello', 'world']
```

### `update_state(state_string, lines) → state_string`

Records a new version of the file. Call this at commit time with the full new content. The function diffs against the previous version internally and updates the state accordingly.

```python
state = update_state(state, ['hello', 'brave', 'world'])
```

### `merge_states(state1, state2) → (state_string, annotated_lines)`

Merges two diverged states. Returns both the merged state (for future merges) and a list of lines with conflict annotations where applicable. When there are no conflicts, `current_lines(state_string)` and `annotated_lines` contain the same content.

```python
merged_state, annotated = merge_states(branch_a, branch_b)
```

## How It Works

The state is a *weave* — a single linear structure containing every line which has ever existed in the file, interleaved with metadata. Its size is linear on the number of lines that have ever appeared in the file's history, which is nice for compactness — the entire history of a file lives in one structure not much bigger than the longest version. Granted, git can get away with being extremely wasteful on storage given how small source code is and how big hard drives are now, but it's a pleasant property to have. Each line is tracked with three pieces of metadata:

- **Depth** — Encodes the tree structure of insertions, so the algorithm knows which lines were inserted relative to which others.
- **Anchor direction** — Whether a line was inserted above or below its neighbor, preserving positional intent across merges. This is a standard CRDT technique for sequence types.
- **Generation count** — An integer which increments on each add/delete cycle. Odd means present, even means deleted. When merging, the higher count wins, ensuring that the most recent knowledge about a line's status is preserved.

During a merge, both states are converted into trees based on their depth/anchor metadata. The trees are then walked in parallel: shared lines are reconciled by their generation counts, and lines unique to one side are inserted at the correct position. Because everything is structural, there needs to be a deterministic tiebreak when two different branches add lines in the exact same position. The algorithm decides — simplifying a bit — by which side has its first line come lexically first. Conflicts are detected when concurrent edits (e.g., one side inserted while the other deleted in the same region) cannot be auto-resolved.

## Why Generation Counting

Most people will accept generation counting as simply reasonable, but it's worth justifying the choice. When you delete a line that was previously added, there's a question of interpretation: is this a forward proactive deletion, or a local undo? If you want structural merging which doesn't depend on checking specific merge IDs in the history, you basically have to do generation counting. The alternative — trying to go whole hog on interpreting deletions as local undos — leads to cases that get very complex and difficult to reason about, while generation counting is trivial.

Generation counting also has the nice property that it never produces a result where two truly identical things merge into something different. (The `AYYB` example in the cherry-picking section is a case where things look superficially similar but are structurally not the same thing.)

The best way to see what a mess the local undo interpretation creates is the criss-cross case:

```
    History:

          0:AB
         /    \
      1:AXB  3:AXB
        |      |
      2:AB   4:AB


    Merge endpoints — obvious answer:

      2:AB   4:AB
         \    /
       merge → AB ✓


    But merge across the branches:

      1:AXB   4:AB           3:AXB   2:AB
         \    /                 \    /
       merge → AXB            merge → AXB
       (local undo)           (local undo)
              \                /
               merge → AB ???
               ^ has to be AB by eventual consistency
                 but looks like neither parent!
```

Start with `AB` (point 0). One branch goes to `AXB` (point 1) then back to `AB` (point 2). Another branch independently goes from point 0 to `AXB` (point 3) then back to `AB` (point 4). Merging points 2 and 4 should obviously give `AB`. But there's a problem. If you merge points 1 and 4, the local undo interpretation gives you a clean merge to `AXB`. Merging points 3 and 2 also gives `AXB`. But then merging those two `AXB` results together — by the eventual consistency rule and just plain common sense — should produce `AB`, which is a strange result where the child looks like neither of its parents. Out of sheer pragmatism, I gave up on calculating those cases and, worse, figuring out how they should be presented in conflicts, and went with generation counting.

## On Diff Algorithms

This implementation uses Python's built-in `SequenceMatcher` for diffing. A production system should use a better diff algorithm — git's histogram diff is probably the current state of the art. Since the exact interpretation of a diff gets baked into the state at commit time, the quality of the diff algorithm directly affects the quality of the structural history.

## The Cherry-Picking Problem

There are three approaches to cherry-picking in a CRDT-based system, and two of them are traps.

**Approach 1: Squashed patches.** Apply the net effect of a series of commits as a single new commit. This can lead to truly bizarre behavior where merges between identical-looking code produce repeated lines. Here's why:

Consider a file containing `AB`. Two different branches both change it to `AXB`. Those merge cleanly as `AXB` — no conflict, no duplication. But now consider the case where each branch arrived at `AXB` via a different route. One branch went `AB` → `AYXB` → `AXB` (inserted Y, then deleted Y). The other went `AB` → `AXYB` → `AXB` (inserted Y after X, then deleted Y). Because `AYXB` and `AXYB` should clearly merge to `AYXYB`, and merging that with either branch's deletion of X results in `AYYB`, the eventual consistency properties of the CRDT require that merging the two `AYB` states also produces `AYYB` — even though both sides look identical.

This isn't a bug. It's deeply necessary for eventual consistency. The lesson is: when using this kind of system, either don't apply squashed patches, or if you do, make sure the un-squashed history is stowed away and never merged back in.

**Approach 2: Replaying exact patches.** Cherry-pick by applying the exact same patches in the exact same order. This works — the structurally determined property guarantees identical states — but it's fragile. You need exactly the right sequence of diffs, and any deviation breaks the equivalence.

**Approach 3: History-range selection.** Select a range of lines in the state whose history you want to cherry-pick and apply that slice directly. This is the right approach. The state format used here supports it — each line carries enough metadata to be extracted and transplanted. Lines which anchor the cherry-picked range but aren't themselves part of it would be included at generation count zero, meaning they're structurally present but invisible. The UX for this hasn't been implemented yet.

## Local Undo

Local undo — reverting a change on one branch without affecting others — is tricky in any version control system.

In a CRDT system, the rebase approach means creating a new fictional history in which the change or merge never happened in the first place — unlike the rebase discussion later in this document, here throwing out the history is the whole point. It's the same nightmare as always: it works, but you have to painstakingly avoid accidentally merging in the non-rebased branch. One wrong merge and the undone change comes back.

A better approach is to use cherry-picking. You make the undo locally, then create a de-undo branch and merge it into main. This has some quirks — in particular, the de-undo can itself have erroneous conflicts with main if the section in question was otherwise modified there. But it mostly works and behaves reasonably. When it acts off, it produces false positives on conflicts, and they're presented reasonably, which is much better than false negatives.

## Rebase Without Destroying History

Rebase as conventionally done in git is history-destroying, but that isn't fundamental to the concept of rebase.

Consider a case: on a local branch you forked from version 0 on main, then made local changes to get version 1 then version 2. Meanwhile main has been updated to version 3. The "merge" way of updating your branch is to merge together versions 2 and 3 and fix conflicts. The "rebase" way is to replay your commits on top of the new main: merge versions 1 and 3 and fix conflicts to get version 4, then merge 4 and 2 and fix conflicts to get version 5.

```
    Merge approach:

      0 → 1 → 2
       \       \
        3 ----merge


    Rebase approach:

      0 → 1 → 2
       \   \    \
        3 merge→4 merge→5
```

The only thing necessary for this to both keep the history and preserve rebase semantics is that version 4 should remember that 3 is its "primary" ancestor and version 5 should remember that 4 is its "primary" ancestor — advisory information which could be stored in the DAG. Following this methodology would get the benefits of a clean rebased history without so many erroneous conflicts and dangerous traps.

It's worth noting that aggressive rebasing this way quickly produces merge topologies with no single latest common ancestor. Approaches which rely on 3-way merge are likely to blow up in your face here — git's recursive merge strategy exists specifically to paper over this problem, and it's fragile. CRDTs handle it just fine, because the history is encoded in the weave itself rather than reconstructed from the DAG at merge time. The whole concept of LCA becomes irrelevant.

## Status

The state maintained by this algorithm is a *weave* (the term of art) — a single structure which interleaves all historical lines with metadata about when they were added and removed. The implementation doesn't currently support history or blame, but adding it would be straightforward. You'd maintain the DAG of versions alongside the weave, attaching commit IDs to each generation increment. Reconstructing a historical version means tracing the DAG to find which diffs were added or removed in each version, then doing a pass over the weave to decide which lines to include and in what order — picking up blame information along the way if that's of interest.

The exact serialization format used is meant as a demo, not a standard. That said, it isn't far from a reasonable one.

## Running Tests

The test suite is built into the module:

```bash
python manyana.py
```

All test functions prefixed with `test` are discovered and run automatically. No output means all tests passed.

## Provenance

The code in this project was written artisanally. This README was not.

## License

Public domain.
