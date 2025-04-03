# services/ai_service.py
import os
import json
import logging
import requests

logger = logging.getLogger(__name__)

class AIService:
    """Service for analyzing logs using Verizon Inspire API."""
    
    def __init__(self):
        """Initialize the AI service with API endpoint and token from environment."""
        self.agents_url = os.getenv('INSPIRE_AGENTS_URL')
        self.agents_token = os.getenv('INSPIRE_AGENTS_TOKEN')
    
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
            
            # Convert logs to a readable format for the AI
            log_text = ""
            for log in logs:
                log_text += f"[{log.get('timestamp')}] [{log.get('level')}] {log.get('message')}\n"
            
            # Prepare the prompt for the AI
            prompt = f"""
            Analyze the following system logs and identify any errors or issues:
            
            {log_text}
            
            Please provide:
            1. A list of all error messages found
            2. The likely root cause of each error
            3. The severity level (Critical, High, Medium, Low)
            
            Format your response as JSON with the structure:
            {{
                "errors": [
                    {{
                        "message": "Error message text",
                        "root_cause": "Likely cause of the error",
                        "severity": "Severity level",
                        "timestamp": "When the error occurred"
                    }}
                ],
                "summary": "Brief summary of the issues found"
            }}
            """
            
            # Prepare the request data
            data = {
                "variables": {
                    "prompt": prompt
                },
                "model": "VEGAS",
                "model_settings": {
                    "temperature": 0.8,
                    "max_output_tokens": 3200
                }
            }
            
            # Prepare the inference URL and headers
            inference_url = f"{self.agents_url}/inference/generate"
            headers = {
                'X-api-key': self.agents_token,
                'Content-Type': 'application/json'
            }
            
            logger.debug("Sending logs to Verizon Inspire AI for analysis")
            
            # Make the API request
            response = requests.post(inference_url, json=data, headers=headers, timeout=60)
            
            if response.status_code != 200:
                logger.error(f"AI API error: {response.status_code} - {response.text}")
                return {
                    "errors": [],
                    "summary": f"Error from AI service: {response.status_code}"
                }
            
            # Extract the AI response
            ai_response = response.json().get('ai_response', '')
            
            # Try to extract JSON from the response
            try:
                # Look for JSON in the response
                json_start = ai_response.find('{')
                json_end = ai_response.rfind('}') + 1
                
                if json_start >= 0 and json_end > json_start:
                    json_str = ai_response[json_start:json_end]
                    analysis = json.loads(json_str)
                else:
                    # Fallback if no JSON is found
                    analysis = {
                        "errors": [],
                        "summary": "No structured analysis available."
                    }
            except json.JSONDecodeError:
                # Handle case where response is not valid JSON
                analysis = {
                    "errors": [],
                    "summary": "Could not parse the analysis response."
                }
            
            # Add raw response for debugging
            analysis["raw_response"] = ai_response
            
            logger.info(f"Analysis complete. Found {len(analysis.get('errors', []))} errors.")
            return analysis
            
        except Exception as e:
            logger.error(f"Error analyzing logs with AI service: {str(e)}")
            return {
                "errors": [],
                "summary": f"Error during analysis: {str(e)}"
            }
