import logging
import json

def extract_data_from_api(**kwargs):
    ti = kwargs['ti']
    api_result = ti.xcom_pull(task_ids='fetch_fpl_api_data')
    logging.info("API Result:", api_result)

    if not api_result:
        logging.error("API result not found in XCom")

    api_result_dict = json.loads(api_result)
    
    return api_result_dict['events'], api_result_dict['teams'], api_result_dict['elements'], api_result_dict['element_types']