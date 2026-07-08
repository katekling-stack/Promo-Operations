# Region → Country selection guide (FreeWheel geo targeting)

How the team targets geography: search the country by **name** in the
FreeWheel *Add New Country* panel and select it. This guide maps each
region code we use in Order/Placement names to the exact country name(s)
to select — and the FW country ID the tool writes under the hood.

The IDs come from the FreeWheel `content_territories` taxonomy, verified
against the UI (e.g. United States = 165). Refresh anytime with
`FreeWheelClient.sync_countries()`; the full table lives in
`data/geo/seed_countries.csv` (251 countries).

| Region code | Select in FreeWheel (Country =) | FW country ID | Tier 1? |
|---|---|---|---|
| USA | United States | 165 | yes |
| CA | Canada | 27 | yes |
| AU | Australia | 10 | yes |
| LATAM | Mexico; Argentina; Chile; Colombia; Peru; Brazil | 114, 8, 32, 35, 125, 21 | yes |
| BR | Brazil | 21 | yes |
| UK | United Kingdom | 56 | no |

## Notes

- **USA** is domestic (Pluto category uses the `Promo Category` prefix).
- **LATAM** is a representative multi-country set — refine per campaign brief.
- To add a region or change its countries, edit `config/regions.yaml`
  (`countries:` list of names). The tool resolves names → IDs automatically;
  an unmatched name is reported, never guessed.
- Full country → ID reference: `data/geo/seed_countries.csv`.
