# POLYBOT Brain Mesh Activation

Phase: `POLYBOT_BRAIN_MESH_ACTIVATION`

## Purpose

This phase wires the existing Brain Mesh services into the autonomous runtime cycle when SYSTEM power is `ON`.

The activation is non-executing. It does not create orders, fills, positions, order intents, paper orders, shadow actions, or live actions.

## Runtime Flow

During `MarketService.refresh()`, after the existing intelligence refresh completes, `BrainMeshActivationService.run_activation()` runs:

1. `RuntimeProducerEvidenceService.run_runtime_evidence_loop()`
2. `RuntimeBrainAdapterService.run_runtime_brain()`
3. `RuntimeCoordinatorDecisionService.run_runtime_coordinator()`
4. `ThesisProfileService.build_profiles()`
5. Non-executing `position_thesis_profiles` bridge from runtime coordinator decisions with real `market_id`

SYSTEM `OFF` prevents the scheduler from reaching `MarketService.refresh()`. The activation service also checks System Power and State Governor before doing any work.

## Persistence

Activation summaries are stored in `brain_mesh_activation_runs`.

The table records cycle ids, status, component output counts, safety deltas, timestamps, and error details.

## Dashboard

`GET /dashboard/api/v2/brain-mesh-activation` reports:

- activation allowed
- latest activation timestamp/status
- latest run summary
- counts created by the latest activation
- latest brain/coordinator/thesis timestamps
- safety deltas
- `mock_data=false`

## Safety Contract

- SYSTEM OFF blocks activation.
- SYSTEM ON activates the mesh but does not enable paper, shadow, or live execution.
- Existing manual diagnostic endpoints remain available, but they are no longer the only way to wake the Brain Mesh.
- Downstream Risk, Exit, and Eligibility remain separate safety gates.
- Position thesis records created here are `NEEDS_REVIEW`, `paper_ready=false`, and `live_ready=false`.
