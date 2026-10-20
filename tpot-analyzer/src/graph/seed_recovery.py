"""Graph-only retrieval. No text, judgments, identity guesses or persistence.

Ranks break equal scores by exact ID for display; evaluation uses the *end* of
the tied block and also reports the possible (start-of-block) recovery ceiling.
"""
from collections import Counter, defaultdict

from src.graph.source_selectivity import rank_follow_candidates

METHODS = ('popularity', 'shared', 'selectivity', 'two_hop')
METHOD_LABELS = {'popularity':'Popularity baseline', 'shared':'Shared seed neighbors',
    'selectivity':'Selective seed neighbors', 'two_hop':'One + two-hop walk'}


class RecoveryGraph:
    def __init__(self, edges):
        self.edges = frozenset((a,b) for a,b in edges if a != b)
        self.adj = defaultdict(set)
        self.popularity = Counter()
        self.nodes = set()
        for source,target in self.edges:
            self.adj[source].add(target)
            self.popularity[target] += 1
            self.nodes.update((source,target))
        self._contributions = {}

    def contribution(self, seed, method):
        """A fixed seed's contribution is independent of every judgment/fold."""
        key = (seed,method)
        if key not in self._contributions:
            if method not in METHODS:raise ValueError('Unknown recovery method')
            values = Counter()
            neighbors = self.adj.get(seed,set())
            if method == 'shared':values.update(neighbors)
            elif method == 'selectivity':
                ranked = rank_follow_candidates([seed], ((seed,node) for node in neighbors))
                values.update({row.account_id:row.selectivity_score for row in ranked.candidates})
            elif method == 'two_hop' and neighbors:
                # Half one-step, half two-step observed-degree-normalized mass.
                # Dangling second steps lose mass, never invent edges/restarts.
                for neighbor in sorted(neighbors):
                    values[neighbor] += .5/len(neighbors)
                    onward = self.adj.get(neighbor,set())
                    for target in sorted(onward):
                        values[target] += .5/len(neighbors)/len(onward)
            self._contributions[key] = values
        return self._contributions[key]

    def rank(self, seeds, method):
        if method not in METHODS:raise ValueError('Unknown recovery method')
        seeds = set(seeds)
        scores = Counter(self.popularity) if method=='popularity' else Counter()
        if method != 'popularity':
            for seed in sorted(seeds):scores.update(self.contribution(seed,method))
        return [{'accountId':account,'score':score} for account,score in
            sorted(scores.items(),key=lambda item:(-item[1],item[0]))
            if account not in seeds and score>0]

    def paths(self, seeds, account, max_hops=2, limit=3):
        """One deterministic shortest witness per supporting seed, not all paths."""
        paths = []
        for seed in sorted(set(seeds)):
            adjacent = self.adj.get(seed,set())
            if account in adjacent:paths.append([(seed,account)])
            elif max_hops==2:
                parent = next((node for node in sorted(adjacent)
                    if account in self.adj.get(node,set())),None)
                if parent is not None:paths.append([(seed,parent),(parent,account)])
            if len(paths)==limit:break
        return paths


def _fold(rows, account):
    for index,row in enumerate(rows):
        if row['accountId'] != account:continue
        score = row['score']
        # Exact deterministic scores; no tolerance that could reorder neighbors.
        return {'accountId':account,'rank':index+1,
            'bestRank':1+sum(item['score']>score for item in rows),
            'worstRank':sum(item['score']>=score for item in rows)}
    return {'accountId':account,'rank':None,'bestRank':None,'worstRank':None}


def evaluate_recovery(graph, positive, negative):
    """Hide only the target label, not its edges. OUT labels only score exposure.

    Every supplied positive stays in the denominator, including isolated nodes.
    No cross-tag/ego inputs. These folds are transductive and retrospective, not
    independent samples or a prospective holdout. No precision is identifiable.
    """
    positive,negative = set(positive),set(negative)
    if len(positive)<3:raise ValueError('Recovery requires at least three IN examples')
    if positive & negative:raise ValueError('IN and OUT examples must be disjoint')
    total = len(positive)
    covered = len(positive & graph.nodes)
    reachable = sum(bool(graph.paths(positive-{account},account,limit=1)) for account in positive)
    results = {}
    for method in METHODS:
        folds = [_fold(graph.rank(positive-{account},method),account) for account in sorted(positive)]
        metrics = {}
        for k in (10,25,50):
            hits = sum(row['worstRank'] is not None and row['worstRank']<=k for row in folds)
            possible = sum(row['bestRank'] is not None and row['bestRank']<=k for row in folds)
            metrics['at'+str(k)] = {'hits':hits,'possibleHits':possible,'recall':hits/total}
        full = graph.rank(positive,method)
        results[method] = {'label':METHOD_LABELS[method], 'total':total,
            'covered':covered,'reachable':reachable,'folds':folds, **metrics,
            'outAt25':len({row['accountId'] for row in full[:25]} & negative),
            'candidateCount':len(full),'rankedCount':sum(row['rank'] is not None for row in folds)}
    return {'methods':results,'positiveCount':total,'negativeCount':len(negative),
        'coveredPositiveCount':covered,'reachablePositiveCount':reachable}
