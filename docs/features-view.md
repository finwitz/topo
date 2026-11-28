# Features view: design draft

Status: first version built 26 November (`pipeline/features.py`, the viewer's Features view, the
Saleor example). Decided 26 November:

- Gaps come from both the code and a reference list.
- The first use is evaluating your own products, from their code. The reference list is then most
  often your own roadmap, PRD or backlog ("promised against built"), or a competitor's public
  feature list. Comparing several products in a grid comes later.

## What it answers

A Topo map is laid out the way the code is: applications, subsystems, modules, files. Someone
evaluating a product asks a different question: what does it do, feature by feature, how complete is
each one, and what is missing? A feature usually cuts across the code (Saleor's checkout touches the
API, the Dashboard and the payment apps), so the map cannot answer that today.

The features view is a second way into the same map: a tree of the product's features, each one
linked to the boxes that implement it, with its status and its gaps.

## What counts as a feature

A feature is something a user can reach, backed by code. Every feature names at least one **entry
point** and cites the boxes behind it. Entry points, by kind of project:

- HTTP routes (`routes.py` already finds them) and GraphQL queries and mutations
- UI pages and screens (route tables, page components)
- CLI commands, MCP tools, public library API
- jobs and webhooks a user turns on or configures

Three levels at most: **area** (Checkout) > **feature** (Gift cards) > **sub-feature** (optional).
Names follow the map's rules (at most 48 characters, a plain one-line summary).

Anchoring on entry points is what keeps two runs from producing two different trees, and keeps the
view checkable like the rest of Topo.

## Status: from the code

Worked out by a script from the cited boxes, never typed by an agent:

| Mark | Meaning | Evidence |
|---|---|---|
| ● built | code reaches it from an entry point | cited boxes with paths |
| ◐ partial | some of it is a stub, partial or behind a flag | a cited box's `status`, or a flag in its facts |
| ◌ docs only | documented, no code found | every cited box is `"source": "docs"` |
| ○ not found | on the reference list, nowhere in the code | see below |

Not built yet: facts shown on a feature without counting as gaps (UI with no backend call, an API
with no UI, no tests near its files).

## Gaps: from a reference list

The user supplies a list: a competitor's feature list, a PRD, an RFP, a category checklist, or
another Topo map's features. Each item ends up in one of three states:

- **matched**: it cites the feature that covers it
- **not found**: nothing in the map covers it. The agent records the terms it searched for, and a
  script runs those terms over the checkout and the map's names. A hit sends the item to
  **check by hand** instead.
- **out of scope**: the user marked it so

An absence cannot cite a line of code, so the view never says "missing": it says "not found
(searched for: saved cart, wishlist, persist checkout)". Not-found items are drawn dashed, like
docs-only boxes.

## Data: `features.json` in the map folder

An overlay like `flows.json`, not part of the code hierarchy:

```json
{
  "features": [
    {"id": "feat.checkout", "name": "Checkout", "summary": "..."},
    {"id": "feat.checkout.gift-cards", "parent": "feat.checkout", "name": "Gift cards",
     "summary": "Shoppers pay with a gift card; staff issue and send them.",
     "entry": ["core.checkout.gql#checkoutAddPromoCode"], "boxes": ["core.checkout.giftcards"],
     "flows": []}
  ],
  "reference": {"name": "Commerce checklist", "source": "reference/commerce.md",
                "items": [{"text": "Saved carts", "state": "not found",
                           "searched": ["saved cart", "persist checkout", "wishlist"]}]}
}
```

`build.py` adds the derived status, the facts and the per-feature box counts into `topo-data.json`.

## Pipeline: one step after the map

1. `features.py brief`: from the finished map only (names, summaries, entry points, flows), not the
   code again. The 35 Saleor flows are a ready seed.
2. One agent (Sonnet) writes `features.json`, and matches the reference list if there is one.
3. `featurecheck.py`, like `symcheck` and `depthcheck`:
   - every id it cites exists, and every feature cites boxes with paths
   - entry-point coverage: the share of the map's entry points that some feature claims (the
     unclaimed ones are listed, since they are features the tree forgot)
   - every reference item is in one of the three states, and the not-found searches are re-run
4. `finish.py` runs it when the map has a `features.json`.

Cost, measured on the Saleor example (three repositories, 2,120 boxes, an 18-item checklist):
about 3.5 million tokens (91% read from cache, 64 thousand written) and 13 minutes on Sonnet, against
36 to 61 million tokens for a gallery map. The tree came out at 8 areas and 39 features, claiming 68
of 70 endpoints and 34 of 35 flows; of the checklist, 13 matched, 2 not found and 3 to check by hand,
each checked in the code.

## The view

- A switch between **Map** and **Features** in the viewer.
- A left-to-right tree: the product at the root, one colour per area (the region colours), each
  leaf with its name, one-line summary, status mark and box count. Branches collapse; large
  products start with areas folded.
- Clicking a feature switches to the map and lights up its boxes, reusing the capability
  highlight, with a panel listing its entry points, boxes and flows.
- A **Gaps** filter: only partial, docs-only and not-found items, plus the reference list's score
  (matched / not found / check by hand).
- On a phone, an outline list in place of the tree.
- Export as SVG (shares the work with issue #6).

Later: the map server gains `topo_features` (the tree, or the feature a file belongs to).

## Relation to capabilities

Maps of client work already tag actions with `capabilities` and compare them across engagements.
In code maps, the feature tree's leaves become that vocabulary, so the existing highlight and the
"has it / lacks it" table work on features without a second concept.

## Later

- **Compare**: a grid of features against products, from several maps or reference lists. A grid
  reads better than two trees side by side.
- Closed products can only come in as reference lists, since Topo reads code.

## Open questions

1. Is three levels enough, or do large products need a fourth?
2. Where a reference list lives: beside the map (`reference/`), so a private roadmap stays in the
   map's own folder, outside this repository like the rest of a user's map.
