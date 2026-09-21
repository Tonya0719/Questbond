"""Session-scoped staff gate for the shared-password hackathon demo."""
import hmac
import time
import streamlit as st
from ..config import settings


def staff_password(role):
    configured = settings.coordinator_password if role == 'Coordinator' else settings.technician_password
    if configured:
        return configured
    if settings.app_env == 'development':
        return 'DispatchOps2026!' if role == 'Coordinator' else 'DispatchTech2026!'
    return None


def authorize_view():
    role = st.sidebar.selectbox('Workspace', ['Customer', 'Technician', 'Coordinator'], key='sign_in_role')
    if st.session_state.get('staff_role') and st.session_state['staff_role'] != role:
        st.session_state.pop('staff_role', None)
    if role == 'Customer':
        st.sidebar.markdown('''<div class="permission-note"><strong>Customer access</strong><br>Book and track a visit without signing in. Staff workspaces are password protected.</div>''', unsafe_allow_html=True)
        return role
    if st.session_state.get('staff_role') == role:
        st.sidebar.success(f'Signed in as {role}')
        if st.sidebar.button('Sign out'):
            appearance = st.session_state.get('dispatch_appearance', 'System')
            st.session_state.clear()
            st.session_state['dispatch_appearance'] = appearance
            st.rerun()
        return role
    st.title('Mendigo')
    st.subheader(f'{role} sign in')
    st.caption('Enter your team’s shared password to access this workspace.')
    expected = staff_password(role)
    if not expected:
        st.error('Staff sign-in is not configured. Set the role password on the server.')
        return None
    if settings.app_env == 'development':
        st.caption('Hackathon demo: shared role access. Individual staff accounts are not enabled.')
    blocked_until = st.session_state.get('sign_in_blocked_until', 0)
    if time.monotonic() < blocked_until:
        st.warning('Too many attempts. Wait one minute before trying again.')
        return None
    with st.form('staff_sign_in', clear_on_submit=True):
        password = st.text_input('Password', type='password')
        submit = st.form_submit_button('Sign in', type='primary')
    if submit:
        if hmac.compare_digest(password.encode(), expected.encode()):
            st.session_state['staff_role'] = role
            st.session_state.pop('sign_in_attempts', None)
            st.session_state.pop('sign_in_blocked_until', None)
            st.rerun()
        else:
            attempts = st.session_state.get('sign_in_attempts', 0) + 1
            st.session_state['sign_in_attempts'] = attempts
            if attempts >= 5:
                st.session_state['sign_in_blocked_until'] = time.monotonic() + 60
                st.session_state['sign_in_attempts'] = 0
            st.error('Incorrect password. Check the password for the selected role.')
    return None
