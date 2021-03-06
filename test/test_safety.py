import unittest
import networkx as nx

from py4j.protocol import Py4JNetworkError
from prismhandler.prism_handler import PrismHandler
from safety_assumptions import minimal_safety_edges
from advisers import simplest_adviser


class TestSafety(unittest.TestCase):

    def setUp(self):
        """
        Creates a mock stochastic game where player 1 can only win if edge (2,3) is never chosen.
        Sets up the PRISM-games java API gateway.
        """
        self.test_game = nx.DiGraph()
        self.test_game.graph['init'] = ('1',)
        self.test_game.graph['acc'] = [('5',)]
        self.test_game.graph['ap'] = ['START', 'GOAL']
        self.test_game.graph['env_ap'] = ['NAUGHTY', 'NICE']
        self.test_game.add_node(('1',), player=1, ap='10')
        self.test_game.add_node(('5',), player=1, ap='01')
        self.test_game.add_node(('6',), player=1, ap='00')
        self.test_game.add_node(('2',), player=2)
        self.test_game.add_node(('7',), player=2)
        self.test_game.add_node(('3',), player=0)
        self.test_game.add_node(('4',), player=0)
        self.test_game.add_node(('8',), player=0)
        self.test_game.add_edge(('1',), ('2',), act='ask')
        self.test_game.add_edge(('5',), ('7',), act='restart')
        self.test_game.add_edge(('2',), ('3',), guards=['10'])
        self.test_game.add_edge(('2',), ('4',), guards=['01'])
        self.test_game.add_edge(('3',), ('6',), prob=1.0)
        self.test_game.add_edge(('4',), ('5',), prob=1.0)
        self.test_game.add_edge(('7',), ('1',), prob=1.0)

        try:
            self.prism_handler = PrismHandler()
            print('Successfully connected to PRISM java gateway!')
        except Py4JNetworkError as err:
            print('Py4JNetworkError:', err)
            print('It is most likely that you forgot to start the PRISM java gateway. '
                  'Compile and launch prismhandler/PrismEntryPoint.java!')

    def test_minimal_safety_edges(self):
        """
        check if the algorithm finds exactly the one edge that needs to be avoided in order for player 1 to win
        """
        safety_edges = minimal_safety_edges(self.test_game, 'test', self.prism_handler, test=True)
        self.assertEqual(len(safety_edges), 1)
        edge = safety_edges[0]
        self.assertEqual(edge[0], ('2',))
        self.assertEqual(edge[1], ('3',))

    def test_simplest_safety_adviser(self):
        """
        check if the constructed safety adviser from that edge has the correct structure
        """
        safety_edges = minimal_safety_edges(self.test_game, 'test', self.prism_handler, test=True)
        ssa = simplest_adviser(self.test_game, safety_edges, 'safety')
        self.assertEqual(ssa.pre_ap, ['START', 'GOAL'])
        self.assertEqual(ssa.adv_ap, ['NAUGHTY', 'NICE'])
        self.assertEqual(ssa.adv_type, 'safety')
        self.assertEqual(ssa.adviser, {'1X': {'10'}})
        self.assertEqual(ssa.pre_init, '10')
