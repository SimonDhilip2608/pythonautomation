# app.py
import streamlit as st
import os
import json
from datetime import datetime
from dotenv import load_dotenv
import logging
from logging.handlers import RotatingFileHandler
import traceback
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(PROJECT_DIR, 'logs')

# Create logs directory if it doesn't exist
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)
    
log_file_path = os.path.join(LOG_DIR, 'log_advisor_log')

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    handlers=[logging.StreamHandler(), 
                             RotatingFileHandler(log_file_path, maxBytes=5242880, backupCount=3)])
logger = logging.getLogger(__name__)

load_dotenv()

# Import services
from services.elk_service import ELKService
from services.vegasgpt_service import VegasGPTService
from services.workflow_service import WorkflowService
from services.workflow_analyzer import WorkflowAnalyzer
from database_model import DatabaseModel

# Set up Streamlit page
st.set_page_config(
    page_title="Log Advisor",
    page_icon="🔍",
    layout="wide"
)

st.title("Log Advisor")
st.markdown("**THE SMART Solution provider with VZGPT/SYNAPT**")
st.markdown("---")

# Initialize database model
db_model = DatabaseModel()

# Initialize the database schema and sample data if required
if 'db_initialized' not in st.session_state:
    with st.spinner("Initializing database..."):
        db_initialized = db_model.init_database()
        if db_initialized:
            db_model.insert_sample_data()
        st.session_state.db_initialized = True

# Initialize services
elk_service = ELKService()
vegasgpt_service = VegasGPTService()
workflow_service = WorkflowService()
workflow_analyzer = WorkflowAnalyzer(db_model)

# Try to get applications from database
try:
    # Get a list of applications from database
    conn = db_model.get_connection()
    if conn is None:
        st.error("Could not connect to database. Please check your database connection.")
        applications = []
    else:
        with conn.cursor() as cursor:
            cursor.execute("""
            SELECT id, app_name, app_code, description
            FROM synapt_dev_db.applications
            WHERE is_active = TRUE
            ORDER BY app_name;
            """)
            applications = [{"id": row[0], "app_name": row[1], "app_code": row[2], "description": row[3]} 
                            for row in cursor.fetchall()]
        
        if not applications:
            st.warning("No applications found in the database. Default sample data will be used.")
            # Insert sample data if no applications exist
            db_model.insert_sample_data()
            
            # Try again
            with conn.cursor() as cursor:
                cursor.execute("""
                SELECT id, app_name, app_code, description
                FROM synapt_dev_db.applications
                WHERE is_active = TRUE
                ORDER BY app_name;
                """)
                applications = [{"id": row[0], "app_name": row[1], "app_code": row[2], "description": row[3]} 
                                for row in cursor.fetchall()]
except Exception as e:
    logger.error(f"Error retrieving applications: {str(e)}")
    logger.error(traceback.format_exc())
    st.error(f"Error retrieving applications: {str(e)}")
    applications = []

# Create application options for dropdown
application_options = {f"{app['id']}: {app['app_name']}": app for app in applications}

# Create a session state to store selected application data and analysis results
if 'selected_app' not in st.session_state:
    st.session_state.selected_app = None
if 'workflow_data' not in st.session_state:
    st.session_state.workflow_data = None
if 'logs' not in st.session_state:
    st.session_state.logs = None
if 'error_analysis' not in st.session_state:
    st.session_state.error_analysis = None
if 'workflow_analysis' not in st.session_state:
    st.session_state.workflow_analysis = None

st.header("Search Parameters")

with st.form("log_search_form"):
    col1, col2 = st.columns(2)
    
    with col1:
        work_order = st.text_input("ELK Transaction ID")
        start_date = st.date_input("Last Transaction Start Date")
        start_time = st.time_input("Last Transaction Start Time")

    with col2:
        # Application dropdown
        application = st.selectbox(
            "Application",
            options=list(application_options.keys()),
            help="Select the application to analyze logs for"
        )
        end_date = st.date_input("Last Transaction End Date")
        end_time = st.time_input("Last Transaction End Time")

    # Using just columns 3 and 4 for analysis types
    with st.columns(1)[0]:
        # Add options for analysis types
        analysis_options = st.multiselect(
            "Analysis Types",
            options=["Log Analysis", "Workflow Analysis", "Comparative Analysis"],
            default=["Log Analysis", "Workflow Analysis", "Comparative Analysis"],
            help="Select which types of analysis to perform"
        )

    submit_button = st.form_submit_button("Analyze Order")

if submit_button:
    if not work_order:
        st.error("Work Order is a required field")
    elif not application:
        st.error("Please select an application")
    elif end_time <= start_time and end_date <= start_date:
        st.error("End time must be after start time")
    else:
        # Get selected application data
        selected_app = application_options[application]
        st.session_state.selected_app = selected_app
        
        # Clear previous results
        st.session_state.workflow_data = None
        st.session_state.logs = None
        st.session_state.error_analysis = None
        st.session_state.workflow_analysis = None
        
        progress_bar = st.progress(0)
        st.markdown("### Analysis Progress")
        status_text = st.empty()
        
        # Step 1: Retrieve logs from ELK
        status_text.text(f"Retrieving logs from ELK for order {work_order} and application {selected_app['app_name']}...")
            
        start_datetime = datetime.combine(start_date, start_time)
        end_datetime = datetime.combine(end_date, end_time)

        start_time_str = start_datetime.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
        end_time_str = end_datetime.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
            
        logs = elk_service.retrieve_logs(
            work_order, 
            start_time_str, 
            end_time_str
        )
        st.session_state.logs = logs
        progress_bar.progress(25)
        
        # Step 2: Retrieve workflow data from Order API
        status_text.text(f"Retrieving workflow details for order {work_order}...")
        workflow_data = workflow_service.get_workflow_details(work_order)
            
        if workflow_data:
            st.session_state.workflow_data = workflow_data
        else:
            st.warning(f"No workflow data found for order {work_order}")
        progress_bar.progress(50)
        
        # Step 3: Get success pattern for comparison
        status_text.text(f"Getting success pattern for comparison...")
        success_samples = db_model.get_success_samples(selected_app['id'])
        success_pattern = db_model.get_workflow_success_pattern(selected_app['id'])
        
        # Format success pattern for AI
        success_pattern_text = "SUCCESS PATTERN:\n\n"
        if success_pattern and 'workflow_sequence' in success_pattern:
            if isinstance(success_pattern['workflow_sequence'], str):
                sequence_data = json.loads(success_pattern['workflow_sequence'])
            else:
                sequence_data = success_pattern['workflow_sequence']
            
            for i, step in enumerate(sequence_data):
                success_pattern_text += f"{i+1}. Task: {step.get('task')}, Domain: {step.get('domain')}, Critical: {step.get('critical', False)}\n"
        
        # Format success samples for AI
        success_samples_text = "\nSUCCESS SAMPLES:\n\n"
        if success_samples:
            for sample in success_samples:
                success_samples_text += f"Task: {sample.get('wf_task_name')}\n"
                success_samples_text += f"Domain: {sample.get('domain')}\n"
                success_samples_text += f"Expected Status: {sample.get('expected_status')}\n"
                success_samples_text += f"Expected Response Code: {sample.get('expected_response_code')}\n"
                success_samples_text += f"Expected Response Description: {sample.get('expected_response_desc')}\n"
                success_samples_text += f"Sequence: {sample.get('task_sequence')}\n"
                success_samples_text += f"Critical: {sample.get('is_critical', False)}\n\n"
        
        success_reference = success_pattern_text + success_samples_text
        progress_bar.progress(75)
        
        # Step 4: Perform AI analysis with logs, workflow data, and success reference
        status_text.text(f"Performing AI analysis on all available data...")
        
        # Format workflow data for AI
        workflow_formatted = workflow_service.format_workflow_for_analysis(workflow_data) if workflow_data else "No workflow data available."
        
        # Combined analysis prompt for VegasGPT
        combined_analysis = vegasgpt_service.analyze_logs(
            logs=logs,
            workflow_data=f"{workflow_formatted}\n\n{success_reference}",
            app_code=selected_app.get('app_code')
        )
        
        st.session_state.error_analysis = combined_analysis
        progress_bar.progress(100)
        status_text.text("Analysis complete!")
        
        # Display results
        st.markdown("## Analysis Results")
        
        tab1, tab2, tab3 = st.tabs(["Retrieved Logs", "Transaction Details", "Analysis & Insights"])
        
        with tab1:
            st.subheader(f"Logs for {selected_app['app_name']} ({len(logs) if logs else 0})")
            
            if logs:
                log_level_filter = st.multiselect(
                    "Filter by Log Level",
                    options=["INFO", "WARNING", "ERROR", "DEBUG", "TRACE"],
                    default=["ERROR", "WARNING"]
                )
                
                filtered_logs = [log for log in logs if log.get('level', '').upper() in log_level_filter]
                
                st.text(f"Showing {len(filtered_logs)} of {len(logs)} logs")
                
                for log in filtered_logs:
                    level = log.get('level', '').upper()
                    timestamp = log.get('timestamp', '')
                    message = log.get('message', '')
                    service = log.get('service', 'unknown')
                    
                    if level in ['ERROR', 'SEVERE']:
                        st.error(f"[{timestamp}] [{service}] {message}")
                    elif level in ['WARNING', 'WARN']:
                        st.warning(f"[{timestamp}] [{service}] {message}")
                    else:
                        st.info(f"[{timestamp}] [{service}] {message}")
            else:
                st.warning("No logs were found for the specified criteria.")
        
        with tab2:
            st.subheader(f"Transaction Details for Order {work_order}")
            
            if workflow_data:
                st.text(f"Found {len(workflow_data)} workflow tasks")
                
                # Create a dataframe for better visualization
                workflow_table = []
                for item in workflow_data:
                    workflow_table.append({
                        "Task Name": item.get('wf_task_name', 'Unknown'),
                        "Status": item.get('status', 'Unknown'),
                        "Response Code": item.get('resp_status_code', 'Unknown'),
                        "Response Desc": item.get('resp_status_desc', 'Unknown'),
                        "Domain": item.get('domain', 'Unknown'),
                        "Start Time": item.get('transaction_start_time', 'Unknown'),
                        "End Time": item.get('transaction_end_time', 'Unknown')
                    })
                
                df = pd.DataFrame(workflow_table)
                st.dataframe(df)
                
                # Compare with success pattern
                if success_samples:
                    st.subheader("Comparison with Success Pattern")
                    
                    comparison_data = []
                    task_status = {}
                    
                    # Map actual workflow data by task name
                    for item in workflow_data:
                        task_name = item.get('wf_task_name')
                        if task_name:
                            task_status[task_name] = {
                                'status': item.get('status'),
                                'response_code': item.get('resp_status_code'),
                                'domain': item.get('domain')
                            }
                    
                    # Create comparison table
                    for sample in success_samples:
                        task_name = sample.get('wf_task_name')
                        actual = task_status.get(task_name, {})
                        
                        status_match = actual.get('status') == sample.get('expected_status')
                        code_match = actual.get('response_code') == sample.get('expected_response_code')
                        
                        comparison_data.append({
                            "Task": task_name,
                            "Domain": sample.get('domain'),
                            "Expected Status": sample.get('expected_status'),
                            "Actual Status": actual.get('status', 'Missing'),
                            "Status Match": "✅" if status_match else "❌",
                            "Expected Code": sample.get('expected_response_code'),
                            "Actual Code": actual.get('response_code', 'Missing'),
                            "Code Match": "✅" if code_match else "❌",
                            "Critical": "Yes" if sample.get('is_critical', False) else "No"
                        })
                    
                    comparison_df = pd.DataFrame(comparison_data)
                    st.dataframe(comparison_df)
                    
                # Add expandable sections for detailed view of each workflow item
                for i, item in enumerate(workflow_data):
                    with st.expander(f"Details: {item.get('wf_task_name', 'Task')} ({item.get('status', 'Unknown')})"):
                        st.json(item)
            else:
                st.warning("No workflow data found for the specified order number.")
                
        with tab3:
            st.subheader(f"AI Analysis and Insights for Order {work_order}")
            
            if combined_analysis:
                # Display the AI summary
                st.markdown("### Summary")
                st.markdown(f"{combined_analysis.get('summary', 'No summary available')}")
                
                # Display AI detected errors
                if combined_analysis.get('errors'):
                    st.subheader("Detected Issues")
                    
                    for i, error in enumerate(combined_analysis.get('errors', [])):
                        severity = error.get('severity', 'Unknown')
                        severity_color = {
                            'Critical': 'red',
                            'High': 'orange',
                            'Medium': 'yellow',
                            'Low': 'blue',
                            'Unknown': 'gray'
                        }.get(severity, 'gray')
                        
                        with st.expander(f"Issue #{i+1}: {error.get('message', '')[:50]}...", expanded=i == 0):
                            st.markdown(f"**Severity**: :{severity_color}[{severity}]")
                            st.markdown("**Error Message**:")
                            st.code(error.get('message', 'No message available'))
                            
                            st.markdown("**Root Cause**:")
                            st.write(error.get('root_cause', 'Unknown'))
                            
                            if error.get('entities_involved'):
                                st.markdown("**Entities Involved**:")
                                entities = error.get('entities_involved', [])
                                if isinstance(entities, list):
                                    for entity in entities:
                                        st.write(f"- {entity}")
                                else:
                                    st.write(entities)
                            
                            if error.get('sql_error'):
                                st.markdown("**SQL Error**:")
                                st.code(error.get('sql_error'))
                            
                            if error.get('timestamp'):
                                st.caption(f"Occurred at: {error.get('timestamp')}")
                else:
                    st.success("No issues detected by AI analysis.")
                    
                # Display AI recommendations if available
                if combined_analysis.get('recommendations'):
                    st.subheader("Recommendations")
                    for i, rec in enumerate(combined_analysis.get('recommendations', [])):
                        st.markdown(f"{i+1}. {rec}")
            else:
                st.warning("No AI analysis available. This could be due to missing data or no issues found.")

# Sidebar with application information and service status
with st.sidebar:
    st.header("About Log Advisor")
    st.markdown("""
    **Log Advisor** helps you:
    
    - Retrieve system logs from ELK
    - Get workflow details from order services
    - Compare with success patterns
    - Analyze logs and workflow data using AI
    - Provide insights and recommendations
    
    Enter your search parameters and click "Analyze Order" to get started.
    """)
    
    st.markdown("---")
    
    st.subheader("Configuration")
    
    # Database initialization/reset option
    if st.button("Reset Database & Sample Data"):
        with st.spinner("Reinitializing database..."):
            db_model.init_database()
            success = db_model.insert_sample_data()
            if success:
                st.success("Database reinitialized with sample data")
            else:
                st.error("Failed to reinitialize database")
    
    st.markdown("---")
    
    st.subheader("Service Status")
    elk_status = ":green[Connected]" if elk_service.is_configured() else ":red[Not Configured]"
    vegas_status = ":green[Connected]" if vegasgpt_service.is_configured() else ":red[Not Configured]"
    workflow_status = ":green[Connected]" if workflow_service.is_configured() else ":red[Not Configured]"
    db_status = ":green[Connected]" if db_model.get_connection() is not None else ":red[Not Connected]"
    
    st.markdown(f"ELK Service: {elk_status}")
    st.markdown(f"Vegas GPT Service: {vegas_status}")
    st.markdown(f"Workflow Service: {workflow_status}")
    st.markdown(f"Database: {db_status}")

    # Service Testing Expanders
    with st.expander("Database Details"):
        if db_model.get_connection() is not None:
            st.text(f"Host: {db_model.db_host}")
            st.text(f"Database: {db_model.db_name}")
            st.text(f"User: {db_model.db_user}")

            if st.button("Test DB Connection"):
                conn = db_model.get_connection()
                if conn is not None:
                    st.success("Database connection successful")
                else:
                    st.error("Database connection failed")
        else:
            st.error("Database not connected")
            
    with st.expander("ELK Service Details"):
        if elk_service.is_configured():
            st.text(f"Host: {elk_service.es_host}")
            st.text(f"Index: {elk_service.elk_index}")

            if st.button("Test ELK Connection"):
                success, message = elk_service.test_connection()
                if success:
                    st.success(message)
                else:
                    st.error(message)
        else:
            st.error("ELK service not configured")
    
    with st.expander("Workflow Service Details"):
        if workflow_service.is_configured():
            st.text(f"API URL: {workflow_service.api_url}")
            
            if st.button("Test Workflow API Connection"):
                success, message = workflow_service.test_connection()
                if success:
                    st.success(message)
                else:
                    st.error(message)
        else:
            st.error("Workflow service not configured")
