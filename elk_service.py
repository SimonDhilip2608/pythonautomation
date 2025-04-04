# services/elk_service.py
import os
import requests
import logging
import base64
import traceback

logger = logging.getLogger(__name__)

class ELKService:
    """Service for retrieving logs from ELK."""
    
    def __init__(self):
        """Initialize the ELK service with endpoint and credentials from environment."""
        self.api_endpoint = os.getenv('ELK_API_ENDPOINT')
        self.username = os.getenv('ELK_USERNAME')
        self.password = os.getenv('ELK_PASSWORD')
        
        # Debug logging for configuration
        if not self.api_endpoint:
            logger.warning("ELK_API_ENDPOINT environment variable is not set")
        if not self.username:
            logger.warning("ELK_USERNAME environment variable is not set")
        if not self.password:
            logger.warning("ELK_PASSWORD environment variable is not set")
    
    def is_configured(self):
        """Check if the service is properly configured."""
        is_config = bool(self.api_endpoint and self.username and self.password)
        logger.debug(f"ELK Service configured: {is_config}")
        return is_config
    
    def test_connection(self):
        """Test the connection to the ELK service."""
        if not self.is_configured():
            return False, "ELK Service is not configured properly"
            
        try:
            # Create Basic Auth header from username and password
            auth_str = f"{self.username}:{self.password}"
            auth_bytes = auth_str.encode('ascii')
            auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
            
            # Make a simple API request to test the connection
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Basic {auth_b64}"
            }
            
            # Try to access cluster health endpoint first as it usually has less access restrictions
            response = requests.get(
                f"{self.api_endpoint}/_cluster/health",
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                cluster_info = response.json()
                status = cluster_info.get('status', 'unknown')
                cluster_name = cluster_info.get('cluster_name', 'unknown')
                return True, f"Successfully connected to ELK cluster '{cluster_name}' (status: {status})"
            else:
                # If cluster health fails, try a simple index check
                # This is useful in environments where users don't have cluster-level access
                response = requests.get(
                    f"{self.api_endpoint}/_cat/indices?format=json",
                    headers=headers,
                    timeout=10
                )
                
                if response.status_code == 200:
                    index_count = len(response.json())
                    return True, f"Successfully connected to ELK. Found {index_count} indices."
                else:
                    return False, f"Failed to connect to ELK: {response.status_code} - {response.text}"
                
        except Exception as e:
            logger.error(f"Error testing ELK service connection: {str(e)}")
            logger.error(traceback.format_exc())
            return False, f"Error connecting to ELK service: {str(e)}"
    
    def retrieve_logs(self, work_order, task_name, start_time, end_time, max_logs=1000):
        """Retrieve logs from ELK based on the provided parameters."""
        if not self.is_configured():
            logger.error("ELK Service is not configured properly")
            return None
            
        try:
            # Create Basic Auth header from username and password
            auth_str = f"{self.username}:{self.password}"
            auth_bytes = auth_str.encode('ascii')
            auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
            
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
                "Authorization": f"Basic {auth_b64}"
            }
            
            logger.info(f"Retrieving logs for work order {work_order} and task {task_name}")
            
            # The actual Elasticsearch endpoint
            search_endpoint = f"{self.api_endpoint}/_search"
            
            # Alternative approach using a specific index
            # search_endpoint = f"{self.api_endpoint}/logs-*/_search"
            
            response = requests.post(
                search_endpoint,
                headers=headers,
                json=query,
                timeout=30
            )
            
            # Alternative method using the requests auth parameter
            # response = requests.post(
            #     search_endpoint,
            #     auth=(self.username, self.password),
            #     headers={"Content-Type": "application/json"},
            #     json=query,
            #     timeout=30
            # )
            
            if response.status_code != 200:
                logger.error(f"ELK API error: {response.status_code} - {response.text}")
                return None
            
            # Extract and format the log entries
            result = response.json()
            hits = result.get('hits', {}).get('hits', [])
            
            if not hits:
                logger.info(f"No logs found for work order {work_order} and task {task_name}")
                return []
            
            logs = []
            for hit in hits:
                source = hit.get('_source', {})
                
                # Handle different potential timestamp fields
                timestamp = source.get('timestamp', source.get('@timestamp', source.get('time', '')))
                
                # Handle different potential log level fields
                level = source.get('level', source.get('log_level', source.get('severity', '')))
                
                # Extract the message field, with fallbacks
                message = source.get('message', source.get('msg', source.get('log_message', '')))
                
                # Create a log entry with flexible field mapping
                log_entry = {
                    'timestamp': timestamp,
                    'level': level,
                    'message': message,
                    'service': source.get('service', source.get('service_name', source.get('application', ''))),
                    'transaction_id': source.get('transaction_id', source.get('txid', source.get('request_id', '')))
                }
                
                # Add any additional fields that might be useful for analysis
                if 'host' in source:
                    log_entry['host'] = source['host']
                if 'error' in source:
                    log_entry['error_details'] = source['error']
                
                logs.append(log_entry)
            
            logger.info(f"Retrieved {len(logs)} logs from ELK")
            return logs
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error connecting to ELK: {str(e)}")
            logger.error(traceback.format_exc())
            return None
        except Exception as e:
            logger.error(f"Error retrieving logs from ELK: {str(e)}")
            logger.error(traceback.format_exc())
            return None
    
    def reset_connection(self):
        """Reset the connection - useful after connection errors."""
        # For HTTP-based services like ELK, there's no persistent connection to reset
        logger.info("Reset called on ELK service - no action needed")
        return True
