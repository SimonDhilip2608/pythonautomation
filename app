# app.py
import streamlit as st
import os
from datetime import datetime
from dotenv import load_dotenv
import json
import logging
from logging.handlers import RotatingFileHandler
import traceback

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

from services.elk_service import ELKService
from services.vegasgpt_service import VegasGPTService
from services.synapt_service import SynaptService

st.set_page_config(
    page_title="Log Advisor",
    page_icon="🔍",
    layout="wide"
)

st.title("Log Advisor")
st.markdown("**THE SMART Solution provider with VZGPT/SYNAPT**")
st.markdown("---")

# Initialize services
elk_service = ELKService()
vegasgpt_service = VegasGPTService()
synapt_service = SynaptService()

# Try to get applications from database
try:
    applications = synapt_service.get_applications()
    if not applications:
        st.error("Could not retrieve applications from database. Please check your database connection.")
        applications = []
except Exception as e:
    logger.error(f"Error retrieving applications: {str(e)}")
    logger.error(traceback.format_exc())
    st.error(f"Error retrieving applications: {str(e)}")
    applications = []

# Create application options for dropdown
application_options = {f"{app['id']}: {app['app_name']}": app for app in applications}

# Create a session state to store selected application data
if 'selected_app' not in st.session_state:
    st.session_state.selected_app = None

st.header("Search Parameters")

with st.form("log_search_form"):
    col1, col2 = st.columns(2)
    
    with col1:
        work_order = st.text_input("Work Order Number")
        start_date = st.date_input("Last Transaction Start Date")
        start_time = st.time_input("Last Transaction Start Time")

    with col2:
        # Replace task_name with application dropdown
        application = st.selectbox(
            "Application",
            options=list(application_options.keys()),
            help="Select the application to analyze logs for"
        )
        end_date = st.date_input("Last Transaction End Date")
        end_time = st.time_input("Last Transaction End Time")

    submit_button = st.form_submit_button("Analyze Logs")

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
        
        # Get application-specific log settings
        log_settings = synapt_service.get_application_log_settings(selected_app['id'])
        elk_index = log_settings.get('elk_index') if log_settings else None
        
        progress_bar = st.progress(0)
        st.markdown("### Analysis Progress")
        status_text = st.empty()
        
        status_text.text(f"Retrieving logs from ELK for order {work_order} and application {selected_app['app_name']}...")
        
        start_datetime = datetime.combine(start_date, start_time)
        end_datetime = datetime.combine(end_date, end_time)

        start_time_str = start_datetime.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
        end_time_str = end_datetime.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
        
        # Use updated retrieve_logs method with application parameters
        logs = elk_service.retrieve_logs(
            work_order, 
            selected_app['id'], 
            selected_app['app_code'], 
            elk_index, 
            start_time_str, 
            end_time_str
        )
        progress_bar.progress(33)
        
        if logs is None:
            st.error("Error connecting to the log service. Please check your connection and try again.")
        elif not logs:
            st.warning(f"No logs found for Work Order {work_order} and Application {selected_app['app_name']} in the specified time range.")
        else:
            status_text.text(f"Analyzing {len(logs)} logs with VZGPT Service...")
            error_analysis = vegasgpt_service.analyze_logs(logs, selected_app['app_code'])
            progress_bar.progress(66)
            
            status_text.text("Finding solutions from Synapt...")
            if error_analysis and error_analysis.get('errors'):
                # Pass application ID to find application-specific solutions
                solution = synapt_service.find_solutions(
                    error_analysis.get('errors'),
                    application_id=selected_app['id']
                )
            else:
                solution = {"recommendations": [], "summary": "No errors to find solutions for."}
            
            progress_bar.progress(100)
            status_text.text("Analysis complete!")
            
            st.markdown("## Analysis Results")
            
            tab1, tab2, tab3 = st.tabs(["Retrieved Logs", "Error Analysis", "Recommended Solutions"])
            
            with tab1:
                st.subheader(f"Logs for {selected_app['app_name']} ({len(logs)})")
                
                log_level_filter = st.multiselect(
                    "Filter by Log Level",
                    options=["INFO", "WARNING", "ERROR", "DEBUG", "TRACE"],
                    default=["INFO", "WARNING", "ERROR"]
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
            
            with tab2:
                if error_analysis and error_analysis.get('errors'):
                    st.subheader(f"Detected Errors in {selected_app['app_name']}")
                    st.markdown(f"**Summary**: {error_analysis.get('summary', 'No summary available')}")
                    
                    for i, error in enumerate(error_analysis.get('errors', [])):
                        with st.expander(f"Error #{i+1}: {error.get('message', '')[:50]}...", expanded=i == 0):
                            st.markdown(f"**Severity**: {error.get('severity', 'Unknown')}")
                            st.markdown("**Error Message**:")
                            st.code(error.get('message', 'No message available'))
                            
                            st.markdown("**Root Cause**:")
                            st.write(error.get('root_cause', 'Unknown'))
                            
                            if error.get('timestamp'):
                                st.caption(f"Occurred at: {error.get('timestamp')}")
                else:
                    st.success(f"No errors detected in the logs for {selected_app['app_name']}.")
            
            with tab3:
                if solution and solution.get('recommendations'):
                    st.subheader(f"Solution Recommendations for {selected_app['app_name']}")
                    st.markdown(f"**Summary**: {solution.get('summary', 'No summary available')}")
                    
                    for i, rec in enumerate(solution.get('recommendations', [])):
                        with st.expander(f"Solution #{i+1}", expanded=i == 0):
                            confidence = rec.get('confidence', 0)
                            confidence_percentage = int(confidence * 100)
                            
                            # Display confidence with color coding
                            if confidence_percentage >= 70:
                                st.markdown(f"**Confidence**: :green[{confidence_percentage}%]")
                            elif confidence_percentage >= 40:
                                st.markdown(f"**Confidence**: :orange[{confidence_percentage}%]")
                            else:
                                st.markdown(f"**Confidence**: :red[{confidence_percentage}%]")
                            
                            st.markdown("**For Error**:")
                            st.code(rec.get('error', 'Unknown error'))
                            
                            st.markdown("**Recommended Fix**:")
                            st.write(rec.get('solution', 'No solution available'))
                            
                            if rec.get('steps'):
                                st.markdown("**Steps to Resolve**:")
                                for j, step in enumerate(rec.get('steps')):
                                    st.markdown(f"{j+1}. {step}")
                else:
                    if error_analysis and error_analysis.get('errors'):
                        st.info(f"No solutions found for the detected errors in {selected_app['app_name']}.")
                    else:
                        st.success(f"No errors detected in {selected_app['app_name']}, no solutions needed.")

with st.sidebar:
    st.header("About Log Advisor")
    st.markdown("""
    **Log Advisor** helps you:
    
    - Retrieve system logs from ELK
    - Analyze logs for errors using Vegas GPT
    - Find solutions from the Synapt knowledge base
    
    Enter your search parameters and click "Analyze Logs" to get started.
    """)
    
    st.markdown("---")
    
    st.subheader("Service Status")
    elk_status = ":green[Connected]" if elk_service.is_configured() else ":red[Not Configured]"
    vegas_status = ":green[Connected]" if vegasgpt_service.is_configured() else ":red[Not Configured]"
    synapt_status = ":green[Connected]" if synapt_service.is_configured() else ":red[Not Configured]"
    
    st.markdown(f"ELK Service: {elk_status}")
    st.markdown(f"Vegas GPT Service: {vegas_status}")
    st.markdown(f"Synapt: {synapt_status}")

    with st.expander("Synapt Database Details"):
        if synapt_service.is_configured():
            st.text(f"Host: {synapt_service.db_host}")
            st.text(f"Database: {synapt_service.db_name}")
            st.text(f"User: {synapt_service.db_user}")

            if st.button("Test Synapt DB Connection"):
                success, message = synapt_service.test_connection()
                if success:
                    st.success(message)
                else:
                    st.error(message)
        else:
            st.error("Synapt database not configured")
            
    with st.expander("Available Applications"):
        if applications:
            for app in applications:
                st.markdown(f"**{app['app_name']}** ({app['app_code']})")
                if app.get('description'):
                    st.markdown(f"_{app['description']}_")
                st.markdown("---")
        else:
            st.warning("No applications available")
