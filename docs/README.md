# Documentation

- [Prototype assessment](PROTOTYPE_ASSESSMENT.md)
- [Glossaire français](GLOSSARY.fr.md)
- [Flux de révision entre canonical et sandbox](CANONICAL_SANDBOX_REVIEW_WORKFLOW.fr.md)
- [Proposition de révision itérative par campagnes](PROPOSITION_BETA_REVIEW_WORKFLOW.fr.md)
- [Contrat de campagne de révision, version 1](CAMPAIGN_CONTRACT_V1.fr.md)
- [État intermédiaire de l'implémentation](INTERMEDIATE_IMPLEMENTATION_STATUS.fr.md)

The application is being adapted incrementally. It currently reads an exported
canonical campaign from GitHub, displays its derived table of contents, and
supports dynamic reference/review language selection. Campaign writes remain
limited to approval-only metadata updates with SHA conflict checks. Question
text and comment writes remain disabled. Documentation in this directory
describes the current behavior and the remaining work before reviewed data can
safely return to the canonical `50ohm-question-pool` repository.
