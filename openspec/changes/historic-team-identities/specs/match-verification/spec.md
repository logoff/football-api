# Spec Delta

## ADDED Requirements

### Requirement: Reference-only Wikidata items

A team in `seeds/teams.yaml` MAY list `reference_wikidata`: other Wikidata items that verification references use for the same side. Verification SHALL read them as the team's own item. They SHALL never be used for identity, and a seed load SHALL fail if one is another team's item.

#### Scenario: Dutch East Indies linked as Indonesia

- **GIVEN** the Dutch East Indies lists Indonesia's item as `reference_wikidata`, and Wikipedia's 1938 World Cup links the side as Indonesia
- **WHEN** verification runs
- **THEN** the Dutch East Indies' 1938 match is compared, not left unpaired
