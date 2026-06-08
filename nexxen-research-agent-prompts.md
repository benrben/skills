# Nexxen DSP Research Agent — Prompt Library

Copy-paste and swap in the ID. Each one drives the agent to the right tools for
that entity type.

### Advertiser
```
Research advertiser {ID}. Pull its profile, list every insertion order and
active publisher deal under it, then give me aggregate performance with the
SSP/channel split and recommendations for the account.
```

### Insertion Order / Campaign
```
Do a full deep-dive on campaign (insertion order) {ID}: config (budget, flight,
KPI, pacing), all packages and line items beneath it, performance vs. target,
a pacing investigation, and a pre-launch/QA config audit.
```

### Package
```
Research package {ID}. Show budget and pacing, list all line items in it with
their budgets, and break down performance by line item and channel.
```

### Line Item
```
Deep-dive line item {ID}: full targeting, bid/max CPM, frequency cap, attached
creatives and deals. Pull performance and win-rate, run a pacing investigation,
and flag any config issues.
```

### Ad
```
Research ad {ID}: its line item, the creative it serves, and the ad's delivery
and performance. Note anything underdelivering.
```

### Creative
```
Research creative {ID}: format, ad size, and which line items run it. Analyze
performance across them and check for creative fatigue (CTR decay over time).
```

### Deal
```
Diagnose publisher deal {ID}: terms (floor, flight, SSP), a full deal-health
check (bid requests seen, floor distribution, targeting mismatch vs. attached
line items), and performance — spend, win rate, eCPM, pacing.
```

### Inventory
```
Research inventory list {ID}: what it contains, its inventory sources, and which
line items reference it.
```

### Location
```
Research location group {ID}: the geos it covers and which line items use it.
```

### Audience / Targeting
```
Research segment {ID} (retargeting/segment/segment set/concept set as
applicable): its definition and size, and where it's attached. Suggest similar
or complementary segments.
```

### Beacon
```
Research beacon {ID}: the advertiser it belongs to, its config, and firing/usage
status across campaigns.
```

### Unknown ID (let the agent route)
```
I have ID {ID} but I'm not sure what type it is. Identify what it is, then run
your full research briefing on it.
```

---

## Power-User Variants

```
Compare deals {ID_A} and {ID_B} head-to-head: terms, health, and performance —
which is delivering better and why?
```

```
For campaign {ID}, find the single biggest reason it's under-pacing and tell me
which line item or SSP is responsible.
```

```
Research advertiser {ID} and surface only my CTV/video performance, split by SSP
— where am I winning and where am I overpaying?
```

---

## Appendix — Read Tool Reference by Entity

| Entity | Primary read tools |
| --- | --- |
| Advertiser | `campaign_getAdvertiser`, `campaign_listInsertionOrders`, `campaign_listPublisherDeals`, `campaign_listBeacons`, `dspai_analyze_reporting` |
| Insertion Order | `campaign_getInsertionOrder`, `campaign_listPackages`, `campaign_listLineItems`, `dspai_investigate_pacing`, `dspai_audit_campaign_config`, `dspai_analyze_reporting` |
| Package | `campaign_getPackage`, `campaign_listLineItems`, `dspai_analyze_reporting` |
| Line Item | `campaign_getLineItem`, `campaign_listAds`, `dspai_investigate_pacing`, `dspai_audit_campaign_config`, `dspai_analyze_reporting` |
| Ad | `campaign_getAd`, `campaign_getCreative`, `dspai_analyze_reporting` |
| Creative | `campaign_getCreative`, `campaign_getAdSize`, `dspai_analyze_reporting` |
| Deal | `campaign_getPublisherDeal`, `dspai_diagnose_deal_health`, `dspai_analyze_reporting` |
| Inventory | `campaign_getInventoryList`, `campaign_listInventorySources` |
| Location | `campaign_getLocationGroup` |
| Audience / Targeting | `campaign_getRetargetingSegment`, `campaign_listSegments`, `campaign_listSegmentSets`, `campaign_listConcepts`, `campaign_listConceptSets` |
| Beacon | `campaign_getBeacon` |
| Account context | `campaign_getCurrentAccount`, `identity_whoami`, `campaign_listFeatureFlags`, `markets_find_markets`, `campaign_listMarkets`, `campaign_listCurrencies` |
| Definitions / how-to | `dspai_ask_helpdesk` |
