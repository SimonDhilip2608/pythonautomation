# services/synapt_service.py
import os
import requests
import logging

logger = logging.getLogger(__name__)

class SynaptService:
    """Service for retrieving solutions from Synapt."""
    
    def __init__(self):
        """Initialize the Synapt service with API endpoint and key from environment."""
        self.api_endpoint = os.getenv('SYNAPT_API_ENDPOINT')
        self.api_key = os.getenv('SYNAPT_API_KEY')
    
    def is_configured(self):
        """Check if the service is properly configured."""
        return bool(self.api_endpoint and self.api_key)
    
    def find_solutions(self, errors):
        """Query Synapt app context to find solutions for the identified errors."""
        if not self.is_configured():
            logger.error("Synapt Service is not configured properly")
            return {"recommendations": [], "summary": "Error: Synapt service not configured."}
            
        try:
            if not errors:
                logger.warning("No errors provided to find solutions for")
                return {
                    "recommendations": [],
                    "summary": "No errors to find solutions for."
                }
            
            # Prepare recommendations container
            recommendations = []
            
            # Process each error to find a solution
            for error in errors:
                error_message = error.get('message', '')
                
                if not error_message:
                    continue
                
                # Prepare the query for Synapt
                query = {
                    "error_message": error_message,
                    "root_cause": error.get('root_cause', ''),
                    "severity": error.get('severity', '')
                }
                
                # Make API request to Synapt
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}"
                }
                
                response = requests.post(
                    f"{self.api_endpoint}/solutions",
                    headers=headers,
                    json=query,
                    timeout=30
                )
                
                if response.status_code != 200:
                    logger.warning(f"Synapt API warning: {response.status_code} - {response.text}")
                    recommendations.append({
                        "error": error_message,
                        "solution": "No solution found in the knowledge base.",
                        "confidence": 0
                    })
                    continue
                
                # Extract the solution
                result = response.json()
                solution = result.get('solution', 'No specific solution found.')
                confidence = result.get('confidence', 0)
                
                recommendations.append({
                    "error": error_message,
                    "solution": solution,
                    "confidence": confidence,
                    "steps": result.get('steps', [])
                })
            
            # Prepare the overall solution response
            solution_response = {
                "recommendations": recommendations,
                "summary": f"Found {len(recommendations)} solution(s) for the identified errors."
            }
            
            return solution_response
            
        except Exception as e:
            logger.error(f"Error finding solutions from Synapt: {str(e)}")
            return {
                "recommendations": [],
                "summary": f"Error retrieving solutions: {str(e)}"
            }