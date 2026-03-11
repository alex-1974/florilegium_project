from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity


class SemanticRanker:

    def __init__(self, topics):

        self.model = SentenceTransformer("all-MiniLM-L6-v2")

        self.topic_embeddings = self.model.encode(topics)


    def score(self, text):

        if not text:
            return 0.0

        emb = self.model.encode([text])

        sim = cosine_similarity(
            emb,
            self.topic_embeddings
        )

        return float(sim.max())
