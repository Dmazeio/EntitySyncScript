# Description
This is a script to sync entities from an external source (csv/xlsx) to Dmaze.
The script is idempotent, so in the case of an error it's fine to re-run with the same input parameters.
This script should run fine on Windows/OSX/Linux. Python3 is required (tested on Python 3.13)

# Installation
Clone this repo (or download the latest release from the release section and unzip).

Install dependencies using either UV or Pip:

## UV
`uv sync`

## Pip
`pip install -r requirements.txt`

# Arguments
The following arguments are supported
| Name | Description | Required |
| ---- | ----------- | -------- |
| --apikey | Dmaze API Key. Can also be set as an environment variable named DMAZE_API_KEY | Yes |
| --config | Path to the config file to use | Yes |
| --entity-type | The EntityName in Dmaze | Yes |
| --csv | Path to the CSV file | Either this or --xlsx is required |
| --xlsx | Path to the XLSX file | Either this or --csv is required |

# Running
Run with either `uv` or `python`.

## Examples
All examples are shown using `python`, but if you are using `uv`, replace `python` with `uv run`

To sync the file `testdata/testdata-1.csv` to an entity type named `testunit` run (from this directory): `python ./main.py --config config.json --entity-type testunit --apikey 'YourApiKeyHere' --csv ./testdata/testdata-1.csv`

To sync the file `testdata/testdata-3.xlsc` to an entity type named `testunit` run (from this directory): `python ./main.py --config config.json --entity-type testunit --apikey 'YourApiKeyHere' --csv ./testdata/testdata-3.xlsx`

We strongly recommend setting the API key to the environment variable `DMAZE_API_KEY`. In that situation the above command becomes:
`python ./main.py --config config.json --entity-type testunit  --csv ./testdata/testdata-1.csv`

# Configuring
The included `config.json` is configured to deal with basic entities. It expects 4 columns, in order:
| Column | Description | Type | Remarks |
| ------ | ----------- | ---- | ------- |
| ExternalID | This is your source system stable ID of the entity | string | |
| ExternalParentId | This is your source system stable Parent ID of the entity | string | If the entity is a top-level entity, set this to 0 |
| name_nb_no | This becomes the name of the entity in Norwegian. | string | |
| name_en_gb | This becomes the name of the entity in English. | string | |
| ExternalDisabled | If the entity is disabled or not | bool | The following values are considered TRUE: 1, '1', True, 'true', 'True', 'TRUE' |

If you need to add more fields to the entity, just expand the config. Each field is defined with the following shape/structure:
```
"fieldname": {
  "index": <The column index (0-based)>,
  "datatype": "string/number/boolean"
}
```

`fieldname` is the field the value will be added to.
`index` is the column index in the csv/xlsx file.
`datatype` is what datatype the value should be read/stored as.

The 5 fields in the default config _must_ be there, or else the script will fail.
