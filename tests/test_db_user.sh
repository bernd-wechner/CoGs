#!/bin/bash
#
# Create the test user with approriate priveleges so the test runner can create clean databases. 

# Define the username and password for the test user
TEST_USER="test_CoGs"
TEST_PASSWORD="ManyTeeth"

# Database to connect to for checks (usually 'postgres' database exists by default)
DB_NAME="postgres"

# Check if the user already exists
# psql -t -P format=unaligned -c "SELECT 1 FROM pg_roles WHERE rolname='${TEST_USER}';"
# -t: suppress headers and footers
# -P format=unaligned: unaligned output (just the value)
# -c: execute command
USER_EXISTS=$(sudo -u postgres psql -d "${DB_NAME}" -t -P format=unaligned -c "SELECT 1 FROM pg_roles WHERE rolname='${TEST_USER}';" 2>/dev/null)

if [ "$USER_EXISTS" == "1" ]; then
    echo "User '${TEST_USER}' already exists."

    # Check if the user has CREATEDB privilege
    # rolcreatedb column is true if the role has CREATEDB privilege
    HAS_CREATEDB=$(sudo -u postgres psql -d "${DB_NAME}" -t -P format=unaligned -c "SELECT rolcreatedb FROM pg_roles WHERE rolname='${TEST_USER}';" 2>/dev/null)

    if [ "$HAS_CREATEDB" == "t" ]; then
        echo "User '${TEST_USER}' already has CREATEDB privilege. No action needed."
    else
        echo "User '${TEST_USER}' exists but lacks CREATEDB privilege. Granting now..."
        sudo -u postgres  psql -d "${DB_NAME}" -c "ALTER ROLE \"${TEST_USER}\" CREATEDB;"
        if [ $? -eq 0 ]; then
            echo "CREATEDB privilege granted to '${TEST_USER}' successfully."
        else
            echo "Failed to grant CREATEDB privilege to '${TEST_USER}'. Check permissions."
        fi
    fi
else
    echo "User '${TEST_USER}' does not exist. Creating and granting CREATEDB privilege..."
    # Create the user and grant CREATEDB in one go (or two commands if preferred)
    sudo -u postgres psql -d "${DB_NAME}" -c "CREATE ROLE \"${TEST_USER}\" WITH LOGIN PASSWORD '${TEST_PASSWORD}';"
    if [ $? -eq 0 ]; then
        echo "User '${TEST_USER}' created successfully."
        sudo -u postgres psql -d "${DB_NAME}" -c "ALTER ROLE \"${TEST_USER}\" CREATEDB;"
        if [ $? -eq 0 ]; then
            echo "CREATEDB privilege granted to '${TEST_USER}' successfully."
        else
            echo "Failed to grant CREATEDB privilege to '${TEST_USER}'. Check permissions."
        fi
    else
        echo "Failed to create user '${TEST_USER}'. Check permissions."
    fi
fi

# Optional: Verify the final state
echo ""
echo "Current privileges for user '${TEST_USER}':"
sudo -u postgres psql -d "${DB_NAME}" -c "\du \"${TEST_USER}\""
