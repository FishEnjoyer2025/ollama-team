# backend/tests/test_planner.py

import unittest
from backend.agents.planner import planner

class TestPlanner(unittest.TestCase):
    def test_partial_failure(self):
        # Arrange
        partial_result = {'completed': True, 'failed': ['task1', 'task2']}

        # Act
        result = planner.handle_partial_failure(partial_result)

        # Assert
        self.assertTrue(result['completed'])
        self.assertEqual(result['failed'], ['task1', 'task2'])

if __name__ == '__main__':
    unittest.main()