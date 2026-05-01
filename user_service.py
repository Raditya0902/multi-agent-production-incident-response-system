def send_notification(self, user_id):
    try:
        # ... (rest of the code)
        if not user_data:
            raise ValueError('User data not found')
        # ... (rest of the code)
    except (AttributeError, ValueError) as e:
        # Log the error and prevent service deregistration
        logging.error(f"Error sending notification: {e}")
        return