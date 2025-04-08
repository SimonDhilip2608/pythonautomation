# services/elk_service.py - Updated with namespace and index support
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
        
        # Add index and namespace configuration
        self.elk_index = os.getenv('ELK_INDEX', 'logs-*')  # Default to logs-*
        self.elk_namespace = os.getenv('ELK_NAMESPACE')
        
        # Debug logging for configuration
        if not self.api_endpoint:
            logger.warning("ELK_API_ENDPOINT environment variable is not set")
        if not self.username:
            logger.warning("ELK_USERNAME environment variable is not set")
        if not self.password:
            logger.warning("ELK_PASSWORD environment variable is not set")
        if not self.elk_index:
            logger.warning("ELK_INDEX environment variable is not set, using default: logs-*")
        
        logger.info(f"ELK Service initialized with index: {self.elk_index}, namespace: {self.elk_namespace or 'None'}")
    
    def is_configured(self):
        """Check if the service is properly configured."""
        is_config = bool(self.api_endpoint and self.username and self.password and self.elk_index)
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
            
            # First try to check if the index exists
            index_url = f"{self.api_endpoint}/{self.elk_index}"
            if self.elk_namespace:
                # Add namespace parameter if specified
                index_url += f"?namespace={self.elk_namespace}"
                
            logger.debug(f"Testing connection to index: {index_url}")
            
            response = requests.head(
                index_url,
                headers=headers,
                timeout=10
            )
            
            if response.status_code in [200, 204]:
                return True, f"Successfully connected to ELK index: {self.elk_index}"
            
            # If index check fails, try a cluster health check
            health_url = f"{self.api_endpoint}/_cluster/health"
            logger.debug(f"Testing connection to cluster health: {health_url}")
            
            response = requests.get(
                health_url,
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                cluster_info = response.json()
                status = cluster_info.get('status', 'unknown')
                cluster_name = cluster_info.get('cluster_name', 'unknown')
                return True, f"Successfully connected to ELK cluster '{cluster_name}' (status: {status})"
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
            
            # Log input parameters
            logger.debug(f"ELK query parameters: work_order={work_order}, task_name={task_name}")
            logger.debug(f"ELK query time range: start={start_time}, end={end_time}")
            
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
            
            # Check if we need to add namespace to the query
            if self.elk_namespace:
                # Add namespace to the query if needed
                # Check if the query structure needs to be adjusted based on your ELK implementation
                query["namespace"] = self.elk_namespace
            
            # Log the complete query as JSON string
            import json
            logger.debug(f"ELK query JSON: {json.dumps(query, indent=2)}")
            
            # Make API request to ELK
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Basic {auth_b64}"
            }
            
            # Log the request URL and headers (excluding auth details)
            search_endpoint = f"{self.api_endpoint}/{self.elk_index}/_search"
            
            # If namespace is specified, add it as a URL parameter
            if self.elk_namespace:
                search_endpoint += f"?namespace={self.elk_namespace}"
                
            logger.debug(f"ELK request URL: {search_endpoint}")
            safe_headers = headers.copy()
            safe_headers["Authorization"] = "Basic ***** (redacted)"
            logger.debug(f"ELK request headers: {safe_headers}")
            
            # Log that we're sending the request
            logger.info(f"Sending request to ELK for work order {work_order} and task {task_name}")
            
            # For debugging, log the exact curl command that would reproduce this request
            curl_command = f"""curl -X POST "{search_endpoint}" \\
-H "Content-Type: application/json" \\
-H "Authorization: Basic *****" \\
-d '{json.dumps(query)}'"""
            logger.debug(f"Equivalent curl command:\n{curl_command}")
            
            # Make the actual request
            response = requests.post(
                search_endpoint,
                headers=headers,
                json=query,
                timeout=30
            )
            
            # Log response status and size
            logger.debug(f"ELK response status: {response.status_code}")
            logger.debug(f"ELK response size: {len(response.text)} bytes")
            
            if response.status_code != 200:
                logger.error(f"ELK API error: {response.status_code} - {response.text}")
                return None
            
            # Extract and format the log entries
            result = response.json()
            
            # Log response metadata
            total_hits = result.get('hits', {}).get('total', {})
            if isinstance(total_hits, dict):  # Elasticsearch 7.x+ format
                total_count = total_hits.get('value', 0)
            else:  # Elasticsearch 6.x format
                total_count = total_hits
                
            logger.debug(f"ELK total hits: {total_count}")
            
            hits = result.get('hits', {}).get('hits', [])
            
            if not hits:
                logger.info(f"No logs found for work order {work_order} and task {task_name}")
                return []
            
            # Log the first hit to understand structure (with sensitive data redacted)
            if hits:
                sample_hit = hits[0].copy()
                if '_source' in sample_hit:
                    # Redact any potentially sensitive fields
                    for field in ['password', 'token', 'api_key', 'secret']:
                        if field in sample_hit['_source']:
                            sample_hit['_source'][field] = "**REDACTED**"
                logger.debug(f"Sample hit structure: {json.dumps(sample_hit, indent=2)}")
            
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
            
            # Log breakdown of log levels for easier debugging
            level_counts = {}
            for log in logs:
                level = log.get('level', 'unknown').upper()
                level_counts[level] = level_counts.get(level, 0) + 1
            
            logger.debug(f"Log level breakdown: {level_counts}")
            
            return logs
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error connecting to ELK: {str(e)}")
            logger.error(traceback.format_exc())
            return None
        except Exception as e:
            logger.error(f"Error retrieving logs from ELK: {str(e)}")
            logger.error(traceback.format_exc())
            return None
