# services/synapt_service.py
import os
import logging
import psycopg2
from psycopg2.extras import RealDictCursor  # For returning results as dictionaries

logger = logging.getLogger(__name__)

class SynaptService:
    """Service for retrieving solutions from Synapt PostgreSQL database."""
    
    def __init__(self):
        """Initialize the Synapt PostgreSQL database connection."""
        # Database connection parameters
        self.db_host = os.getenv('SYNAPT_DB_HOST')
        self.db_port = os.getenv('SYNAPT_DB_PORT')
        self.db_name = os.getenv('SYNAPT_DB')
        self.db_user = os.getenv('SYNAPT_USER')
        self.db_password = os.getenv('SYNAPT_PASSWORD')
        
        # Connection pool or single connection
        self.conn = None
    
    def is_configured(self):
        """Check if the service is properly configured."""
        return bool(self.db_host and self.db_name and self.db_user and self.db_password and self.db_port)
    
    def get_connection(self):
        """Get a database connection."""
        if not self.is_configured():
            logger.error("Synapt database not configured properly")
            return None
            
        try:
            if self.conn is None or self.conn.closed:
                self.conn = psycopg2.connect(
                    host=self.db_host,
                    port=self.db_port,
                    dbname=self.db_name,
                    user=self.db_user,
                    password=self.db_password
                )
            return self.conn
        except Exception as e:
            logger.error(f"Error connecting to Synapt database: {str(e)}")
            return None
    
    def test_connection(self):
        """Test the connection to the Synapt database."""
        if not self.is_configured():
            return False, "Synapt database is not configured properly"
            
        try:
            conn = self.get_connection()
            if conn is None:
                return False, "Could not establish database connection"
                
            with conn.cursor() as cursor:
                cursor.execute("SELECT version();")
                db_version = cursor.fetchone()[0]
                return True, f"Successfully connected to PostgreSQL: {db_version}"
                
        except Exception as e:
            logger.error(f"Error testing Synapt database connection: {str(e)}")
            return False, f"Error connecting to Synapt database: {str(e)}"
    
    def close_connection(self):
        """Close the database connection."""
        if self.conn is not None and not self.conn.closed:
            self.conn.close()
            self.conn = None
    
    def find_solutions(self, errors):
        """
        Query Synapt database to find solutions for the identified errors.
        
        Args:
            errors (list): List of error objects with message, root_cause, and severity
        
        Returns:
            dict: Solutions for the identified errors
        """
        try:
            if not errors:
                logger.warning("No errors provided to find solutions for")
                return {
                    "recommendations": [],
                    "summary": "No errors to find solutions for."
                }
            
            conn = self.get_connection()
            if conn is None:
                return {
                    "recommendations": [],
                    "summary": "Could not connect to solution database."
                }
            
            # Prepare recommendations container
            recommendations = []
            
            # Process each error to find a solution
            for error in errors:
                error_message = error.get('message', '')
                
                if not error_message:
                    continue
                
                try:
                    # Use a cursor that returns dictionaries
                    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                        # Search for solutions by partial matching on error message
                        query = """
                        SELECT 
                            id, 
                            error_message,
                            solution,
                            solution_confidence AS confidence,
                            solution_steps,
                            severity
                        FROM 
                            solutions 
                        WHERE 
                            error_message ILIKE %s
                        ORDER BY
                            solution_confidence DESC
                        LIMIT 1;
                        """
                        
                        # Use ILIKE for case-insensitive pattern matching with % wildcards
                        cursor.execute(query, (f"%{error_message[:50]}%",))
                        result = cursor.fetchone()
                        
                        if result:
                            # Process solution steps if they're stored as text
                            steps = []
                            if result.get('solution_steps'):
                                # Check if stored as a string list or JSON string
                                if isinstance(result['solution_steps'], str):
                                    if result['solution_steps'].startswith('['):
                                        try:
                                            import json
                                            steps = json.loads(result['solution_steps'])
                                        except:
                                            steps = [result['solution_steps']]
                                    else:
                                        steps = [step.strip() for step in result['solution_steps'].split('\n') if step.strip()]
                                elif isinstance(result['solution_steps'], list):
                                    steps = result['solution_steps']
                            
                            recommendations.append({
                                "error": error_message,
                                "solution": result.get('solution', 'No specific solution found.'),
                                "confidence": float(result.get('confidence', 0)),
                                "steps": steps,
                                "id": result.get('id')  # Include the solution ID for reference
                            })
                        else:
                            # No solution found in database
                            recommendations.append({
                                "error": error_message,
                                "solution": "No solution found in the knowledge base.",
                                "confidence": 0,
                                "steps": []
                            })
                
                except Exception as e:
                    logger.error(f"Error querying database for solution: {str(e)}")
                    recommendations.append({
                        "error": error_message,
                        "solution": f"Error retrieving solution: {str(e)}",
                        "confidence": 0,
                        "steps": []
                    })
            
            # Prepare the overall solution response
            solution_response = {
                "recommendations": recommendations,
                "summary": f"Found {len([r for r in recommendations if r.get('confidence', 0) > 0])} solution(s) for {len(recommendations)} identified errors."
            }
            
            return solution_response
            
        except Exception as e:
            logger.error(f"Error finding solutions from Synapt database: {str(e)}")
            return {
                "recommendations": [],
                "summary": f"Error retrieving solutions: {str(e)}"
            }
        finally:
            # Keep connection open for future queries
            pass
    
    def __del__(self):
        """Close connection when object is destroyed."""
        self.close_connection()
