# services/gemini_service.py
import os
import json
import logging
import google.generativeai as genai

logger = logging.getLogger(__name__)

class GeminiService:
    """Service for analyzing logs using Google Gemini."""
    
    def __init__(self):
        """Initialize the Gemini service with API key from environment."""
        self.api_key = os.getenv('GEMINI_API_KEY')
        
        if self.api_key:
            # Configure the Gemini API
            genai.configure(api_key=self.api_key)
    
    def is_configured(self):
        """Check if the service is properly configured."""
        return bool(self.api_key)
    
    def analyze_logs(self, logs):
        """Analyze logs using Google Gemini to identify errors."""
        if not self.is_configured():
            logger.error("Gemini Service is not configured properly")
            return {"errors": [], "summary": "Error: Gemini service not configured."}
            
        try:
            if not logs:
                logger.warning("No logs provided for analysis")
                return {
                    "errors": [],
                    "summary": "No logs available to analyze."
                }
            
            # Convert logs to a readable format for Gemini
            log_text = ""
            for log in logs:
                log_text += f"[{log.get('timestamp')}] [{log.get('level')}] {log.get('message')}\n"
            
            # Prepare the prompt for Gemini
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
            
            # Generate content with Gemini
            model = genai.GenerativeModel('gemini-pro')
            response = model.generate_content(prompt)
            
            # Parse the response and extract structured data
            response_text = response.text
            
            # Try to extract JSON from the response
            try:
                # Look for JSON in the response
                json_start = response_text.find('{')
                json_end = response_text.rfind('}') + 1
                
                if json_start >= 0 and json_end > json_start:
                    json_str = response_text[json_start:json_end]
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
            
            return analysis
            
        except Exception as e:
            logger.error(f"Error analyzing logs with Google Gemini: {str(e)}")
            return {
                "errors": [],
                "summary": f"Error during analysis: {str(e)}"
            }