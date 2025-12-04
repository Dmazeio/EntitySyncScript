import argparse
import pathlib
import pandas
import logging
import os
import json
import requests
import copy
from datetime import datetime, timezone
from collections import deque

DMAZE_ENDPOINT = 'https://api.dmaze.com/'
IDS = deque()
HEADERS_GET = {
  'Accept': 'application/json',
}
HEADERS_PUT = {
}

def get_entity(filter_field: str, filter_value: str, entity_type: str) -> dict|None:
  params = f'filterfield={filter_field}&filtervalue={filter_value}&take=1&includedisabled=true'
  response = requests.get(f"{DMAZE_ENDPOINT}/v3/entity/{entity_type}?{params}", headers=HEADERS_GET)
  if response.status_code == 200:
    data = response.json()
    if len(data) <= 0:
      return None
    return data[0]
  elif response.status_code == 404:
    return None
  else:
    raise Exception(f'Failed to get entity: {response.status_code} {response.text}')

def get_id() -> str:
  if len(IDS) <= 0:
    response = requests.get(f'{DMAZE_ENDPOINT}/id?count=20', headers=HEADERS_GET)
    if response.status_code == 200:
      data = response.json()
      ids = data['results'][0]['ids']
      for id in ids:
        IDS.append(id)
    else:
      raise Exception(f'Failed to get IDs: {response.status_code} {response.text}')

  return IDS.popleft()

def upsert_entity(logger: logging.Logger, entity_type: str, data: dict) -> bool:
  existing_entity = get_entity('externalid', data.get('externalid', ''), entity_type)
  if existing_entity:
    logger.info(f'Updating existing entity with externalid {data.get("externalid", "")}')
  else:
    logger.info(f'Creating entity with externalid {data.get("externalid", "")}')
  
  second_pass = False
  
  external_parent_id = data.get('externalparentid', '0')
  is_root_entity = external_parent_id in ['', '0', 0]
  now = datetime.now(timezone.utc)
  
  if existing_entity is None:
    # try to find parent entity if not root
    if is_root_entity:
      data['parentid'] = '0'
    else:
      parent_entity = get_entity('externalid', external_parent_id, entity_type)
      if parent_entity is not None:
        data['parentid'] = parent_entity['id']
      else:
        data['parentid'] = '0'
        second_pass = True # parent not found, will try again later
    
    data['isexternalentity'] = True
    if data.get('externaldisabled', False):
      data['disabled'] = now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond:06d}0Z"
    else:
      data['disabled'] = None
      
    data['name'] = data.get('name_nb_no', '')
    
    entity_id = get_id()
    data['id'] = entity_id
    response = requests.put(f'{DMAZE_ENDPOINT}/entity/{entity_type}/{entity_id}', headers=HEADERS_PUT, json=data)
    
    if response.status_code != 200:
      raise Exception(f'Failed to create entity: {response.status_code} {response.text}')
    
    return second_pass
  else:
    updated_entity = copy.deepcopy(existing_entity)
    entity_id = existing_entity['id']
    for key, value in data.items():
      updated_entity[key] = value
      
    updated_entity['isexternalentity'] = True
    
    # try to find parent entity if not root
    if not is_root_entity:
      parent_entity = get_entity('externalid', external_parent_id, entity_type)
      if parent_entity is not None:
        updated_entity['parentid'] = parent_entity['id']
      else:
        logger.warning(f"Parent entity with externalid {external_parent_id} not found for entity {data.get('externalid', '')}. Check your source data.")
        return False
    
    external_disabled = data.get('externaldisabled', False)
    if external_disabled and not updated_entity.get('disabled', None):
      updated_entity['disabled'] = now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond:06d}0Z"
    elif not external_disabled and updated_entity.get('disabled', None):
      updated_entity['disabled'] = None
    
    if updated_entity == existing_entity:
      logger.info(f'No changes for entity with externalid {data.get("externalid", "")}, skipping update.')
      return False
    
    response = requests.put(f'{DMAZE_ENDPOINT}/entity/{entity_type}/{entity_id}', headers=HEADERS_PUT, json=updated_entity)
    if response.status_code != 200:
      raise Exception(f'Failed to update entity: {response.status_code} {response.text}')
    
    return False

def main():
  logger = _setup_logger()
  
  parser = argparse.ArgumentParser()
  parser.add_argument('--apikey', default=os.getenv('DMAZE_API_KEY', ''), type=str, help='Dmaze API Key (can be set via DMAZE_API_KEY env variable)')
  parser.add_argument('--config', default='config.json', type=pathlib.Path, required=True, help='Path to config file')
  parser.add_argument('--entity-type', default='', type=str, required=True, help='Dmaze Entity Name')
  parser.add_argument('--csv', default='data.csv', type=pathlib.Path, required=False, help='Path to CSV file with entities')
  parser.add_argument('--xlsx', default='data.xlsx', type=pathlib.Path, required=False, help='Path to Excel file with entities')
  
  args = parser.parse_args()
  
  if args.apikey == '':
    logger.error('API Key is required. Please provide it via --apikey argument or DMAZE_API_KEY environment variable.')
    return
  
  args.config = args.config.resolve()
  if not args.config.exists():
    logger.error(f'Config file {args.config} does not exist.')
    return

  args.csv = args.csv.resolve()
  args.xlsx = args.xlsx.resolve()
  if not args.csv.exists() and not args.xlsx.exists():
    logger.error('At least one of --csv or --xlsx file must be provided and exist.')
    return
  if args.csv.exists() and args.xlsx.exists():
    logger.error('Please provide only one of --csv or --xlsx file, not both.')
    return
  if args.entity_type == '':
    logger.error('Entity type is required. Please provide it via --entity-type argument.')
    return
  
  HEADERS_GET['x-apikey'] = args.apikey
  HEADERS_PUT['x-apikey'] = args.apikey
  
  with open(args.config, 'r', encoding='utf-8') as config_file:
    config = json.load(config_file)
  field_mappings = config.get('fieldMappings', {})
  
  data_mode = 'csv' if args.csv.exists() else 'xlsx'
  reader = pandas.read_csv if data_mode == 'csv' else pandas.read_excel
  
  second_pass_entities = []
  
  for index, row in reader(args.csv if data_mode == 'csv' else args.xlsx, skiprows = 0, dtype=object).iterrows():
    entity = {}
    column_count = len(row)
    
    for field, col_info in field_mappings.items():
      if column_count <= col_info['index']:
        continue
      
      value = row.iloc[col_info['index']]
      
      if col_info.get('datatype') == 'string':
        entity[field] = str(value)
      elif col_info.get('datatype') == 'number':
        entity[field] = int(value)
      elif col_info.get('datatype') == 'boolean':
        if value in [1, '1', True, 'true', 'True', 'TRUE']:
          entity[field] = True
        else:
          entity[field] = False
      else:
        logger.warning(f"Unknown datatype for field {field}, treating as string.")
        entity[field] = str(value)
    
    second_pass = upsert_entity(logger, entity_type=args.entity_type, data=entity)
    if second_pass:
      logger.info(f'Unable to find parent for entity with externalid {entity.get("externalid", "")}, scheduling second update pass')
      second_pass_entities.append(entity)
  
  logger.info(f'Second pass for {len(second_pass_entities)} entities.')
  for entity in second_pass_entities:
    upsert_entity(logger, entity_type=args.entity_type, data=entity)
  
def _setup_logger() -> logging.Logger:
  logger = logging.getLogger('main')
  logger.setLevel(logging.INFO)
  ch = logging.StreamHandler()
  ch.setLevel(logging.INFO)
  formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
  ch.setFormatter(formatter)
  logger.addHandler(ch)

  return logger

def _debug_log(response):
  print("=== REQUEST ===")
  print(response.request.method, response.request.url)
  print("--- Headers ---")
  for k, v in response.request.headers.items():
    print(f"{k}: {v}")
  print("--- Body ---")
  try:
    body = response.request.body
    if isinstance(body, (bytes, bytearray)):
        body = body.decode("utf-8")
    print(json.dumps(json.loads(body), indent=2, ensure_ascii=False))
  except Exception:
    # Fallback if it's not JSON
    print(response.request.body)

if __name__ == "__main__":
  main()
