# services/elk_service.py
import os
import requests
import logging

logger = logging.getLogger(__name__)

class ELKService:
    """Service for retrieving logs from ELK."""
    
    def __init__(self):
        """Initialize the ELK service with API endpoint and key from environment."""
        self.api_endpoint = os.getenv('ELK_API_ENDPOINT')
        self.api_key = os.getenv('ELK_API_KEY')
    
    def is_configured(self):
        """Check if the service is properly configured."""
        return bool(self.api_endpoint and self.api_key)
    
    def retrieve_logs(self, work_order, task_name, start_time, end_time, max_logs=1000):
        """Retrieve logs from ELK based on the provided parameters."""
        if not self.is_configured():
            logger.error("ELK Service is not configured properly")
            return None
            
        try:
            # Format the ELK query
            query = {
                "query": {
                    "bool": {
                        "must": [
                            {"match": {"work_order.keyword": work_order}},
                            {"match": {"task_name.keyword": task_name}},
                            {
                                "range": {
                                    "timestamp": {
                                        "gte": start_time,
                                        "lte": end_time
                                    }
                                }
                            }
                        ]
                    }
                },
                "sort": [{"timestamp": {"order": "asc"}}],
                "size": max_logs
            }
            
            # Make API request to ELK
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"ApiKey {self.api_key}"
            }
            
            response = requests.post(
                f"{self.api_endpoint}/_search",
                headers=headers,
                json=query,
                timeout=30
            )
            
            if response.status_code != 200:
                logger.error(f"ELK API error: {response.status_code} - {response.text}")
                return None
            
            # Extract and format the log entries
            result = response.json()
            hits = result.get('hits', {}).get('hits', [])
            
            if not hits:
                return []
            
            logs = []
            for hit in hits:
                source = hit.get('_source', {})
                logs.append({
                    'timestamp': source.get('timestamp'),
                    'level': source.get('level'),
                    'message': source.get('message'),
                    'service': source.get('service'),
                    'transaction_id': source.get('transaction_id')
                })
            
            return logs
            
        except Exception as e:
            logger.error(f"Error retrieving logs from ELK: {str(e)}")
            return None