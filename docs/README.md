# Documentation

- [Prototype assessment](PROTOTYPE_ASSESSMENT.md)
- [Glossaire français](GLOSSARY.fr.md)
- [Flux de révision entre canonical et sandbox](CANONICAL_SANDBOX_REVIEW_WORKFLOW.fr.md)
- [Proposition de révision itérative par campagnes](PROPOSITION_BETA_REVIEW_WORKFLOW.fr.md)
- [Contrat de campagne de révision, version 1](CAMPAIGN_CONTRACT_V1.fr.md)
- [État intermédiaire de l'implémentation](INTERMEDIATE_IMPLEMENTATION_STATUS.fr.md)
- [Profilage des opérations GitHub](GITHUB_PROFILING.md)
- [Cache de campagne et écritures atomiques](CAMPAIGN_CACHE_AND_WRITES.md)
- [Question review tool design](QUESTION_REVIEW_TOOL_DESIGN.md)
- [Transfert du depot de campagnes vers USKA-FOS](CAMPAIGN_REPOSITORY_TRANSFER_TO_USKA_FOS.fr.md)
- [Petites améliorations à regrouper](SMALL_IMPROVEMENTS_BACKLOG.fr.md)

The application is being adapted incrementally. It currently reads an exported
canonical campaign from GitHub, displays its derived table of contents, and
supports dynamic reference/review language selection. Campaign writes remain
protected by SHA and branch-head conflict checks. One `Commit` action writes
changed text, appends an optional comment, and approves the active language;
`Reopen` restores the open status. Canonical return is handled by the dry-run
and controlled apply tools in `50ohm-question-pool`.

One deployment can expose several configured campaign branches under
`/campaign/<campaign-id>/`. Prefer a mounted multi-line `campaigns.json` file
selected through `CAMPAIGNS_FILE`; `CAMPAIGNS_JSON` remains a compatibility
fallback. The configuration defines public identifiers, branches, labels, and
optional `enabled` flags. Disabled campaigns remain documented in
configuration but cannot be accessed. `DEFAULT_CAMPAIGN` controls the root
redirect when at least one campaign is active. All routes share one GitHub
OAuth callback.
