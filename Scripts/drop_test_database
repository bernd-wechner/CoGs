# Disconnect the processes using the database
echo "Disconnecting users... "
psql --host=localhost  --username=postgres -qc "SELECT pg_terminate_backend(pg_stat_activity.pid) FROM pg_stat_activity WHERE datname = 'CoGs_test'; "
echo "Dropping database... CoGs_test"
psql --host=localhost  --username=postgres -qc 'DROP DATABASE "CoGs_test";'


echo "Disconnecting users... "
psql --host=localhost  --username=postgres -qc "SELECT pg_terminate_backend(pg_stat_activity.pid) FROM pg_stat_activity WHERE datname = 'test_CoGs'; "
echo "Dropping database... test_CoGs"
psql --host=localhost  --username=postgres -qc 'DROP DATABASE "test_CoGs";'