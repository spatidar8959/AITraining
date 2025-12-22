"""
Google Vertex AI Embedding Service
Generates 1408-dimensional embeddings using multimodalembedding@001
"""
import os
import base64
import logging
from typing import List, Optional
from google.api_core.exceptions import GoogleAPIError
from google.cloud.aiplatform_v1 import PredictionServiceClient
from google.cloud import aiplatform

from app.config import settings

# Setup logger
logger = logging.getLogger(__name__)

# Constants
MODEL_NAME = "multimodalembedding@001"
EMBEDDING_DIMENSION = 1408

# Validate configuration
PROJECT_ID = settings.VERTEX_PROJECT
LOCATION = settings.VERTEX_LOCATION
GOOGLE_CREDENTIALS = settings.GOOGLE_APPLICATION_CREDENTIALS

if not PROJECT_ID or not LOCATION or not GOOGLE_CREDENTIALS:
    raise RuntimeError(
        "Missing required Vertex AI config: VERTEX_PROJECT, VERTEX_LOCATION, or GOOGLE_APPLICATION_CREDENTIALS"
    )

ENDPOINT = f"projects/{PROJECT_ID}/locations/{LOCATION}/publishers/google/models/{MODEL_NAME}"

# Set environment and initialize Vertex AI
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = GOOGLE_CREDENTIALS


class EmbeddingService:
    """Google Vertex AI embedding generation service"""

    def __init__(self):
        """Initialize Vertex AI client"""
        self.project_id = PROJECT_ID
        self.location = LOCATION
        self.endpoint = ENDPOINT
        self.prediction_client: Optional[PredictionServiceClient] = None
        self._initialize_client()

    def _initialize_client(self):
        """Initialize Vertex AI prediction client with error handling"""
        try:
            aiplatform.init(project=self.project_id, location=self.location)
            logger.info(f"Vertex AI Platform initialized: project={self.project_id}, location={self.location}")
        except Exception as e:
            logger.critical(f"Vertex AI Platform initialization failed: {e}", exc_info=True)
            raise

        try:
            self.prediction_client = PredictionServiceClient(
                client_options={"api_endpoint": f"{self.location}-aiplatform.googleapis.com"}
            )
            logger.info(f"PredictionServiceClient created successfully")
        except Exception as e:
            logger.critical(f"Failed to create PredictionServiceClient: {e}", exc_info=True)
            raise

    def generate_image_embedding(self, image_bytes: bytes) -> List[float]:
        """
        Generate image embedding using Vertex AI Multimodal Embedding.

        Args:
            image_bytes: Raw image bytes

        Returns:
            List of 1408 floats representing the embedding vector
            Returns empty list on any failure
        """
        if not image_bytes:
            logger.warning("Empty image bytes provided to generate_image_embedding")
            return []

        # Encode to base64
        try:
            image_bytes_base64 = base64.b64encode(image_bytes).decode("utf-8")
        except Exception as e:
            logger.error(f"Base64 encoding of image failed: {e}", exc_info=True)
            return []

        # Prepare instance for Vertex AI
        instances = [{"image": {"bytesBase64Encoded": image_bytes_base64}}]

        # Validate client
        if self.prediction_client is None:
            logger.error("PredictionServiceClient is not initialized")
            return []

        # Make prediction request with timeout
        try:
            response = self.prediction_client.predict(
                endpoint=self.endpoint,
                instances=instances,
                timeout=60  # Increased to 60s for production reliability
            )
        except GoogleAPIError as e:
            logger.error(f"Vertex AI GoogleAPIError: {e}", exc_info=True)
            return []
        except Exception as e:
            logger.error(f"Vertex AI prediction request failed: {type(e).__name__}: {e}", exc_info=True)
            return []

        # Validate response
        if not hasattr(response, "predictions") or not response.predictions:
            logger.warning("Empty predictions returned from Vertex AI")
            return []

        # Extract embedding
        prediction = response.predictions[0]

        # Handle different prediction formats (dict, protobuf MapComposite, etc.)
        if isinstance(prediction, dict):
            image_embedding = prediction.get("imageEmbedding")
        elif hasattr(prediction, "get"):
            image_embedding = prediction.get("imageEmbedding")
        elif hasattr(prediction, "imageEmbedding"):
            image_embedding = prediction.imageEmbedding
        else:
            # Try to access as attribute
            try:
                image_embedding = getattr(prediction, "imageEmbedding", None)
            except:
                logger.error(f"Cannot extract imageEmbedding from prediction type: {type(prediction)}")
                return []

        # Convert protobuf RepeatedComposite to list if needed
        # Vertex AI returns protobuf objects, not plain Python lists
        if image_embedding is not None and not isinstance(image_embedding, (list, tuple)):
            try:
                # Try converting to list (works for protobuf RepeatedComposite)
                image_embedding = list(image_embedding)
                logger.debug(f"Converted imageEmbedding from {type(image_embedding)} to list")
            except (TypeError, ValueError) as e:
                logger.warning(f"Cannot convert imageEmbedding to list. Type: {type(image_embedding)}, Error: {e}")
                return []

        if not isinstance(image_embedding, (list, tuple)):
            logger.warning(f"'imageEmbedding' not found or invalid type after conversion: {type(image_embedding)}. Prediction type: {type(prediction)}")
            return []

        if not image_embedding:
            logger.warning("imageEmbedding is empty")
            return []

        # Validate embedding format
        if not all(isinstance(i, (float, int)) for i in image_embedding):
            logger.warning(f"imageEmbedding has invalid format: {type(image_embedding[0])}")
            return []

        # Convert to list of floats
        embedding_list = list(map(float, image_embedding))

        # Validate dimension
        if len(embedding_list) != EMBEDDING_DIMENSION:
            logger.warning(
                f"Expected {EMBEDDING_DIMENSION} dimensions, got {len(embedding_list)}"
            )

        logger.info(f"Generated image embedding: {len(embedding_list)} dimensions")
        return embedding_list

    def generate_batch_embeddings(self, image_bytes_list: List[bytes]) -> List[Optional[List[float]]]:
        """
        Generate embeddings for multiple images.

        Args:
            image_bytes_list: List of raw image bytes

        Returns:
            List of embeddings (None for failed images)
        """
        embeddings = []
        for idx, image_bytes in enumerate(image_bytes_list):
            try:
                embedding = self.generate_image_embedding(image_bytes)
                embeddings.append(embedding if embedding else None)
            except Exception as e:
                logger.error(f"Batch embedding failed for image {idx}: {e}", exc_info=True)
                embeddings.append(None)

        return embeddings

    def health_check(self) -> bool:
        """
        Verify Vertex AI service is accessible.

        Returns:
            True if service is healthy, False otherwise
        """
        try:
            # Simple validation - check if client exists
            if self.prediction_client is None:
                logger.error("PredictionServiceClient is None in health check")
                return False

            logger.info("Vertex AI health check passed")
            return True
        except Exception as e:
            logger.error(f"Vertex AI health check failed: {e}", exc_info=True)
            return False


# Singleton instance
embedding_service = EmbeddingService()
