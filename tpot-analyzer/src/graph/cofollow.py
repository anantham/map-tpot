"""Fixed observed-degree co-follow arithmetic shared by research and Review.

Walk seed -> shared followee <- candidate. Scores are not probabilities.
No judgments, source loading, account identity resolution or persistence here.
"""
from collections import Counter, defaultdict
import re


class CoFollowGraph:
    def __init__(self, edges):
        self.edges=frozenset((a,b) for a,b in edges if a!=b)
        self.outgoing=defaultdict(set);self.incoming=defaultdict(set)
        self.nodes=set();self.contributions={};self.pools=defaultdict(list)
        for a,b in self.edges:
            self.outgoing[a].add(b);self.incoming[b].add(a);self.nodes.update((a,b))
        for account in sorted(self.nodes):self.pools[self.degree_bin(account)].append(account)

    def degree_bin(self, account):
        """0,1-9,10-99,... observed out-degree strata, not exact matching."""
        return len(str(len(self.outgoing[account]))) if self.outgoing[account] else 0

    def rank(self, seeds):
        seeds=set(seeds);scores=Counter()
        for seed in sorted(seeds):
            if seed not in self.contributions:
                values=Counter();neighbors=self.outgoing[seed]
                for neighbor in sorted(neighbors):
                    mass=1/(len(neighbors)*len(self.incoming[neighbor]))
                    for candidate in sorted(self.incoming[neighbor]):values[candidate]+=mass
                self.contributions[seed]=values
            scores.update(self.contributions[seed])
        return [{'accountId':a,'score':v} for a,v in sorted(scores.items(),key=lambda x:(-x[1],x[0]))
                if a not in seeds and v>0]

    def paths(self, seeds, target, limit=3):
        paths=[]
        for seed in sorted(set(seeds)):
            common=self.outgoing[seed]&self.outgoing[target]
            if common:
                shared=min(common);paths.append([(seed,shared),(target,shared)])
            if len(paths)==limit:break
        return paths


def fold_rank(rows, target):
    for i,row in enumerate(rows):
        if row['accountId']==target:
            return {'accountId':target,'rank':i+1,
                'bestRank':1+sum(r['score']>row['score'] for r in rows),
                'worstRank':sum(r['score']>=row['score'] for r in rows)}
    return {'accountId':target,'rank':None,'bestRank':None,'worstRank':None}


def at25(folds):
    return {'hits':sum(f['worstRank'] is not None and f['worstRank']<=25 for f in folds),
            'possibleHits':sum(f['bestRank'] is not None and f['bestRank']<=25 for f in folds)}


def evaluate_cofollow(graph, positive, negative):
    positive,negative=set(positive),set(negative)
    if len(positive)<3:raise ValueError('At least three IN examples required')
    if positive&negative:raise ValueError('IN and OUT examples must be disjoint')
    folds=[fold_rank(graph.rank(positive-{a}),a) for a in sorted(positive)]
    full=graph.rank(positive)
    return {'total':len(positive),'coveredOutgoing':sum(bool(graph.outgoing[a]) for a in positive),
        'reachable':sum(bool(graph.paths(positive-{a},a)) for a in positive),
        'folds':folds,'at25':at25(folds),
        'outAt25':len({r['accountId'] for r in full[:25]}&negative)}


def shuffle_seeds(graph, seeds, hidden, rng):
    wanted=Counter(graph.degree_bin(a) for a in set(seeds));chosen=set()
    for degree,n in sorted(wanted.items()):
        pool=[a for a in graph.pools[degree] if a!=hidden]
        if len(pool)<n:raise ValueError('Insufficient same-stratum null population')
        chosen.update(rng.sample(pool,n))
    return chosen


def stable_seed_graph(edges):
    """Numeric sources/candidates; historical handle tokens are targets only."""
    edges=set(edges)
    if any(not re.fullmatch('[0-9]+',a) or not re.fullmatch(r'(?:[0-9]+|shadow:[a-z0-9_]{1,15})',b)
           for a,b in edges):raise ValueError('Only numeric sources may become candidates or seeds')
    graph=CoFollowGraph(edges)
    graph.pools=defaultdict(list)
    for account in sorted(graph.nodes):
        if account.isascii() and account.isdigit():graph.pools[graph.degree_bin(account)].append(account)
    return graph
