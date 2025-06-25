import importlib
import unittest
import os
import re

def load_tests(loader, standard_tests, pattern):
    """
    Custom test discovery for the top-level 'tests' package.
    This function manually scans the current directory for test files
    (e.g., 'test_*.py') and loads tests directly from those modules,
    without recursing into subdirectories.

    Args:
        loader: The unittest.TestLoader instance.
        standard_tests: A TestSuite containing any tests that the default
                        discovery mechanism would have found in this location.
                        We ignore this as we're performing custom discovery.
        pattern: The filename pattern used for discovery (e.g., 'test*.py').
                 We'll use a simple check for 'test_*.py' regardless of pattern,
                 but it's good to keep in mind.

    Returns:
        A unittest.TestSuite object containing all discovered tests.
    """
    # Get the absolute path of the directory containing this __init__.py file.
    current_dir = os.path.dirname(os.path.abspath(__file__))

    # Define the pattern for test files using a regular expression.
    # This matches files starting with 'test_', followed by any characters,
    # and ending with '.py'. The '\.' escapes the dot.
    test_file_pattern = r'^test_.*\.py$'
    
    print(f"\nCustom test discovery initiated for '{current_dir}' (non-recursive)")
    print(f"Scanning for files matching '{test_file_pattern}'")

    # Initialize an empty test suite to add our discovered tests to.
    suite = unittest.TestSuite()

    # Iterate through all entries (files and directories) in the current_dir.
    for filename in os.listdir(current_dir):
        # Construct the full path to the file/directory.
        full_path = os.path.join(current_dir, filename)

        # Check if the entry is a file, starts with 'test_', and ends with '.py'.
        if os.path.isfile(full_path) and re.fullmatch(test_file_pattern, filename):
            # Remove the '.py' extension to get the module name.
            module_name = filename[:-3]

            # Construct the full importable path for the module.
            # __name__ here refers to the package name (e.g., 'tests' if your folder is named 'tests').
            # We combine the package name with the module name within that package.
            # The '__main__' check is a safety net, though less common in this context.
            full_import_path = f"{__name__}.{module_name}" if __name__ != "__main__" else module_name

            try:
                # Dynamically import the module using its full import path.
                module = importlib.import_module(full_import_path)
                # Load tests from the imported module and add them to our suite.
                suite.addTests(loader.loadTestsFromModule(module))
                print(f"  Loaded tests from: {full_import_path}")
            except Exception as e:
                # Log any errors encountered while trying to load a test module.
                print(f"  Error loading tests from {full_import_path}: {e}")
                # You could also add a dummy test to indicate a failure to load the module
                # e.g., suite.addTest(unittest.FunctionTestCase(lambda: False, description=f"Failed to load {full_import_path} due to: {e}"))

    print(f"Discovered {suite.countTestCases()} tests in total from '{current_dir}':")
    i = 1
    for test in suite:
        # A test can be a TestSuite itself (e.g., if a module added multiple tests)
        # or an individual TestCase. We need to handle nested suites.
        if isinstance(test, unittest.TestSuite):
            for sub_test in test:
                print(f"\t{i}\t{sub_test.id()}")
                i+=1
        else:
            # If it's a single TestCase
            print(f"\t{i}\t{test.id()}")
            i+=1
    return suite
