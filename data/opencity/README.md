# OpenCity data used for training labels

Downloaded from https://data.opencity.in on 11 November 2026. All files are published there as
"Other (Public Domain)". The originals come from BBMP and KSRSAC.

The OpenCity site was offline on 12 November 2026 (502 Bad Gateway), so these copies are kept in the
repo. When the site is back, the links below fetch the same files.

## Files

| File here | What it is | Rows |
| --- | --- | --- |
| `flood_vulnerable.kml` | BBMP points vulnerable to flooding, with location name, ward and zone | 200 points |
| `flood_prone.kml` | BBMP flood-prone locations | 70 points |
| `low_lying.kml` | BBMP low-lying areas | 129 points |
| `griev_2020.csv` | BBMP grievances, from 8 Feb 2020 | 91,620 |
| `griev_2021.csv` | BBMP grievances 2021 | 103,504 |
| `griev_2022.csv` | BBMP grievances 2022 | 118,394 |
| `griev_2023.csv` | BBMP grievances 2023 | 119,140 |
| `griev_2024.csv` | BBMP grievances 2024 | 207,016 |
| `griev_2025.csv` | BBMP grievances 2025, until 19 Jun 2025 | 126,974 |
| `swd_primary.kml` | Primary stormwater drains, 2022 | 163 lines, 328 km |
| `swd_secondary.kml` | Secondary stormwater drains, 2022 | 870 lines, 439 km |
| `wards_2015.kml` | BBMP ward map, 198 wards (matches the grievance ward names) | 198 |
| `wards_2022.kml` | BBMP ward map, 243 wards | 243 |

Grievance columns: `Complaint ID, Category, Sub Category, Grievance Date, Ward Name, Grievance Status,
Staff Remarks, Staff Name`. Flood labels are the 8,274 rows where `Sub Category` is `water stagnation`.

## Dataset pages

- Flood points: https://data.opencity.in/dataset/flooding-locations-in-bengaluru-urban
- Grievances: https://data.opencity.in/dataset/bbmp-grievances-data
- Stormwater drains: https://data.opencity.in/dataset/bengaluru-stormwater-drains-maps
- Ward maps: https://data.opencity.in/dataset/bbmp-ward-information

Archived copies of the pages (Wayback Machine):

- http://web.archive.org/web/20250215112521/https://data.opencity.in/dataset/flooding-locations-in-bengaluru-urban
- http://web.archive.org/web/20251210122010/https://data.opencity.in/dataset/bbmp-grievances-data

## Direct download links

Flood points:

- flood_vulnerable.kml: https://data.opencity.in/dataset/b03218ea-4b7c-4fa9-ab67-b9054d7ecc4c/resource/a7d8a01f-1fbc-41e1-85f0-f15ea16b2d27/download/6b3c63b0-f461-4e9c-a2c2-006f734c5b41.kml
- flood_prone.kml: https://data.opencity.in/dataset/b03218ea-4b7c-4fa9-ab67-b9054d7ecc4c/resource/d90fe768-caba-4c6e-b6b5-a75acd5e88a9/download/00fb1229-dcfd-4f59-813f-885e0c629add.kml
- low_lying.kml: https://data.opencity.in/dataset/b03218ea-4b7c-4fa9-ab67-b9054d7ecc4c/resource/62ceac3b-f6e2-4dd1-ae9f-be80b1f2fda8/download/8e87a2fc-e014-4c6e-81f1-d5cb4db57a46.kml

Grievances:

- griev_2020.csv: https://data.opencity.in/dataset/54344a76-a37a-4d05-961c-df9bac5494ad/resource/58808356-4b0a-4b02-9d70-75993b4dcd1c/download/413fa9ec-8d06-4ecb-884e-1436c5a0f5dd.csv
- griev_2021.csv: https://data.opencity.in/dataset/54344a76-a37a-4d05-961c-df9bac5494ad/resource/bada528d-f4f5-4ace-9dd1-8ac459fe350b/download/9e7e6892-06b6-4fdc-967a-e4787562f155.csv
- griev_2022.csv: https://data.opencity.in/dataset/54344a76-a37a-4d05-961c-df9bac5494ad/resource/e44f1808-4923-4390-b62c-710d19ab876b/download/b4dd8dd1-1628-4f35-9247-ef5afaad214d.csv
- griev_2023.csv: https://data.opencity.in/dataset/54344a76-a37a-4d05-961c-df9bac5494ad/resource/fae120ab-d95c-4281-aa86-5bf694712472/download/d4419a76-e2af-44b3-aa25-369c85126f0f.csv
- griev_2024.csv: https://data.opencity.in/dataset/54344a76-a37a-4d05-961c-df9bac5494ad/resource/2a3f29ef-a7a1-4fc3-b125-cbcc958a89d1/download/82f88d50-71c5-4203-92ac-5ccb5cabc7a2.csv
- griev_2025.csv: https://data.opencity.in/dataset/54344a76-a37a-4d05-961c-df9bac5494ad/resource/1342a93b-9a61-4766-9c34-c8357b7926c2/download/b0d6e9ff-5eef-48bf-ba86-985dbe8112d1.csv

Stormwater drains:

- swd_primary.kml: https://data.opencity.in/dataset/fc97e05c-c54b-44e9-8d98-7663ee887922/resource/114758e9-c356-46e0-afdb-e1d52f972863/download/03eea514-d4bf-4cd9-8c7b-f904b1ea83f2.kml
- swd_secondary.kml: https://data.opencity.in/dataset/fc97e05c-c54b-44e9-8d98-7663ee887922/resource/4b26cd1b-7956-418d-92e4-35275caf547a/download/7033efa5-2382-4e4a-8884-5715698eac71.kml
- Tertiary drains (25 MB, not downloaded): https://data.opencity.in/dataset/fc97e05c-c54b-44e9-8d98-7663ee887922/resource/aa20362c-9769-46dc-9a88-c100504f6d4e/download/79494624-2682-4f31-a0e5-2fa26b867304.kml

Ward maps:

- wards_2015.kml: https://data.opencity.in/dataset/87b978d1-352e-4b90-aa2c-9991e55d3425/resource/a0329df6-2924-43f4-8fe4-7a6ffcc1d53d/download/806d6b9c-e8d9-4eb0-a3a3-b2ba68ec3cda.kml
- wards_2022.kml: https://data.opencity.in/dataset/87b978d1-352e-4b90-aa2c-9991e55d3425/resource/9423dbca-db2b-47df-823e-8546f4fb8f2a/download/53418b48-c08d-43bd-be0e-31b46cd0f798.kml

## Rain

Rain is not from OpenCity. It comes from the free Open-Meteo archive API (no key):
https://open-meteo.com/en/docs/historical-weather-api
