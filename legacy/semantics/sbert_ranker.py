from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity


class SBERTSemanticRanker:

    def __init__(self, model_name="all-MiniLM-L6-v2"):

        self.model_name = model_name
        self.model = None
        self.topic_embedding = None

    def load(self):

        if self.model is None:
            self.model = SentenceTransformer(self.model_name)

    def set_topic_profile(self, topic_text):

        self.load()
        self.topic_embedding = self.model.encode([topic_text])[0]

    def score(self, text):

        if self.topic_embedding is None:
            raise RuntimeError("Topic profile not set")

        embedding = self.model.encode([text])[0]

        return cosine_similarity(
            [self.topic_embedding],
            [embedding]
        )[0][0]
