# services/vegasgpt_service.py
import os
import json
import logging
import requests
from datetime import datetime

logger = logging.getLogger(__name__)

class VegasGPTService:
    """Service for analyzing logs using Verizon Inspire API."""
    
    def __init__(self):
        """Initialize the AI service with API endpoint and token from environment."""
        self.agents_url = os.getenv('INSPIRE_AGENT_URL')
        self.agents_token = os.getenv('INSPIRE_AGENT_TOKEN')
    
    def is_configured(self):
        """Check if the service is properly configured."""
        return bool(self.agents_url and self.agents_token)
    
    def analyze_logs(self, logs):
        """Analyze logs using the Verizon Inspire API to identify errors."""
        if not self.is_configured():
            logger.error("AI Service is not configured properly")
            return {"errors": [], "summary": "Error: AI service not configured."}
            
        try:
            if not logs:
                logger.warning("No logs provided for analysis")
                return {
                    "errors": [],
                    "summary": "No logs available to analyze."
                }
            
            # Format logs for better analysis
            # Count error logs to ensure we're sending meaningful data
            error_count = 0
            log_text = ""
            
            for log in logs:
                level = log.get('level', '').upper()
                message = log.get('message', '')
                timestamp = log.get('timestamp', '')
                
                # If it's an error/severe log, highlight it for better AI recognition
                if level in ['ERROR', 'SEVERE']:
                    error_count += 1
                    log_text += f"ERROR_LOG: [{timestamp}] {message}\n"
                else:
                    log_text += f"[{timestamp}] [{level}] {message}\n"
            
            logger.info(f"Sending {len(logs)} logs for analysis, including {error_count} error logs")
            
            # Enhanced, more detailed prompt
            prompt = f"""
            You are a system log analyzer specialized in identifying and categorizing errors. 
            
            Analyze the following system logs and extract ALL error messages. Focus on logs that contain 'ERROR' or 'Exception' or error-related terms.
            
            {log_text}
            
            For each detected error:
            1. Extract the full error message
            2. Determine the likely root cause
            3. Assign a severity level (Critical, High, Medium, Low)
            4. Include the timestamp when available
            
            Make sure to include EVERY individual error. Don't generalize or group similar errors - list each one separately.
            
            Format your response ONLY as a JSON object with the structure:
            {{
                "errors": [
                    {{
                        "message": "The EXACT error message text",
                        "root_cause": "Your analysis of the likely cause",
                        "severity": "Severity level",
                        "timestamp": "When the error occurred"
                    }}
                ],
                "summary": "Brief summary of the overall situation"
            }}
            
            If you find no errors, return an empty errors array but still provide a summary.
            """
            
            data = {
                "variables": {
                    "prompt": prompt
                },
                "model": "VEGAS",
                "model_settings": {
                    "temperature": 0.2,  # Lower temperature for more consistent output
                    "max_output_tokens": 4000
                }
            }
            
            inference_url = f"{self.agents_url}/inference/generate"
            headers = {
                'X-api-key': self.agents_token,
                'Content-Type': 'application/json'
            }
            
            logger.debug("Sending logs to Verizon Inspire AI for analysis")
            
            response = requests.post(inference_url, json=data, headers=headers, timeout=120)  # Increased timeout
            
            if response.status_code != 200:
                logger.error(f"AI API error: {response.status_code} - {response.text}")
                return {
                    "errors": [],
                    "summary": f"Error from AI service: {response.status_code}"
                }
            
            # Get the raw response
            ai_response = response.json().get('ai_response', '')
            logger.debug(f"Received response from AI service: {ai_response[:200]}...")  # Log start of response
            
            # Improved JSON extraction logic
            try:
                # Look for JSON in the response
                json_start = ai_response.find('{')
                json_end = ai_response.rfind('}') + 1
                
                if json_start >= 0 and json_end > json_start:
                    json_str = ai_response[json_start:json_end]
                    # Try parsing the JSON
                    analysis = json.loads(json_str)
                    
                    # Validate expected structure
                    if not isinstance(analysis.get('errors'), list):
                        logger.warning("AI response didn't contain errors array")
                        analysis["errors"] = []
                    
                    if "summary" not in analysis:
                        analysis["summary"] = "Analysis completed without summary."
                else:
                    # If no JSON structure found, try to create our own by scanning for error messages
                    logger.warning("No JSON structure found in AI response, parsing raw text")
                    errors = []
                    lines = ai_response.split('\n')
                    for line in lines:
                        if "ERROR" in line or "Exception" in line or "error" in line.lower():
                            errors.append({
                                "message": line.strip(),
                                "root_cause": "Unknown - parsed from unstructured response",
                                "severity": "Unknown",
                                "timestamp": datetime.now().isoformat()
                            })
                    
                    analysis = {
                        "errors": errors,
                        "summary": "Parsed unstructured response for errors."
                    }
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse AI response as JSON: {str(e)}")
                # Fallback analysis - scan for error messages
                errors = []
                lines = ai_response.split('\n')
                for line in lines:
                    if "ERROR" in line or "Exception" in line or "error" in line.lower():
                        errors.append({
                            "message": line.strip(),
                            "root_cause": "Unknown - parsed from unstructured response",
                            "severity": "Unknown",
                            "timestamp": datetime.now().isoformat()
                        })
                
                analysis = {
                    "errors": errors,
                    "summary": "Failed to parse JSON response, extracted errors from raw text."
                }
            
            logger.info(f"Analysis complete. Found {len(analysis.get('errors', []))} errors.")
            
            # Store raw response for debugging but not for UI display
            analysis["_raw_response"] = ai_response
            
            return analysis
            
        except Exception as e:
            logger.error(f"Error analyzing logs with AI service: {str(e)}")
            return {
                "errors": [],
                "summary": f"Error during analysis: {str(e)}"
            }
        

    def test_connection(self):
        """Test the connection to the Vegas GPT service."""
        if not self.is_configured():
            return False, "Vegas GPT Service is not configured properly - missing API token"
            
        try:
            data = {
                "variables": {
                    "prompt": "Return 'Connection successful' as a simple test."
                },
                "model": "VEGAS",
                "model_settings": {
                    "temperature": 0.1,
                    "max_output_tokens": 20
                }
            }
            
            inference_url = f"{self.agents_url}/inference/generate"
            headers = {
                'X-api-key': self.agents_token,
                'Content-Type': 'application/json'
            }
            
            logger.debug(f"Testing connection to: {inference_url}")
            logger.debug(f"Headers: X-api-key: {self.agents_token[:5]}...")
            
            response = requests.post(
                inference_url, 
                json=data, 
                headers=headers, 
                timeout=10
            )
            
            if response.status_code == 200:
                response_json = response.json()
                if 'ai_response' in response_json:
                    return True, "Successfully connected to Vegas GPT service"
                else:
                    return False, f"Connected but received unexpected response format: {response_json}"
            else:
                return False, f"Failed to connect: {response.status_code} - {response.text}"
                
        except Exception as e:
            logger.error(f"Error testing Vegas GPT service connection: {str(e)}")
            return False, f"Error connecting to Vegas GPT service: {str(e)}"
