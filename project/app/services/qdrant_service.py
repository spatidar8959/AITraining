"""
Qdrant Vector Database Service
Handles vector storage and retrieval for trained frame embeddings
"""
import logging
import uuid
from typing import List, Optional, Dict, Any
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from qdrant_client.http import models

from app.config import settings

# Setup logger
logger = logging.getLogger(__name__)


class QdrantService:
    """Qdrant vector database service"""

    def __init__(self):
        """Initialize Qdrant client"""
        self.url = settings.QDRANT_URL
        self.api_key = settings.QDRANT_API_KEY
        self.collection_name = settings.QDRANT_COLLECTION_NAME
        self.embedding_dimension = settings.EMBEDDING_DIMENSION
        self.distance_metric = self._get_distance_metric(settings.QDRANT_DISTANCE_METRIC)
        self.client: Optional[QdrantClient] = None
        self._initialize_client()

    def _get_distance_metric(self, metric_name: str) -> Distance:
        """Convert metric name to Qdrant Distance enum"""
        metric_map = {
            "COSINE": Distance.COSINE,
            "DOT": Distance.DOT,
            "EUCLID": Distance.EUCLID,
            "EUCLIDEAN": Distance.EUCLID,
        }
        return metric_map.get(metric_name.upper(), Distance.COSINE)

    def _initialize_client(self):
        """Initialize Qdrant client with error handling"""
        try:
            if self.api_key:
                self.client = QdrantClient(
                    url=self.url,
                    api_key=self.api_key,
                    timeout=30
                )
            else:
                self.client = QdrantClient(
                    url=self.url,
                    timeout=30
                )
            logger.info(f"Qdrant client initialized: {self.url}")
        except Exception as e:
            logger.critical(f"Failed to initialize Qdrant client: {e}", exc_info=True)
            raise

    def ensure_collection_exists(self) -> bool:
        """
        Create collection if it doesn't exist.

        Returns:
            True if collection exists or was created successfully
        """
        try:
            # Check if collection exists
            collections = self.client.get_collections()
            collection_names = [col.name for col in collections.collections]

            if self.collection_name in collection_names:
                logger.info(f"Collection '{self.collection_name}' already exists")
                return True

            # Create collection
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=self.embedding_dimension,
                    distance=self.distance_metric
                )
            )
            logger.info(
                f"Created Qdrant collection '{self.collection_name}' "
                f"(dim={self.embedding_dimension}, distance={self.distance_metric})"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to ensure collection exists: {e}", exc_info=True)
            return False

    def generate_point_id(self, video_id: int, frame_id: int) -> str:
        """
        Generate unique point ID for Qdrant.

        Returns a UUID string (without prefix) since Qdrant requires either UUID or integer.
        The mapping between video/frame and UUID is stored in MySQL (qdrant_point_id column).

        Args:
            video_id: Video ID (unused, kept for API compatibility)
            frame_id: Frame ID (unused, kept for API compatibility)

        Returns:
            UUID string compatible with Qdrant
        """
        # Generate a pure UUID string (Qdrant accepts UUID format)
        point_id = str(uuid.uuid4())
        return point_id

    def upsert_point(
        self,
        point_id: str,
        embedding: List[float],
        payload: Dict[str, Any]
    ) -> bool:
        """
        Insert or update a single point in Qdrant.

        Args:
            point_id: Unique point identifier
            embedding: Vector embedding (1408 dimensions)
            payload: Metadata dictionary

        Returns:
            True if successful, False otherwise
        """
        try:
            # Validate embedding
            if len(embedding) != self.embedding_dimension:
                logger.error(
                    f"Invalid embedding dimension: expected {self.embedding_dimension}, "
                    f"got {len(embedding)}"
                )
                return False

            # Ensure collection exists
            if not self.ensure_collection_exists():
                logger.error("Collection does not exist and failed to create")
                return False

            # Create point
            point = PointStruct(
                id=point_id,
                vector=embedding,
                payload=payload
            )

            # Upsert to Qdrant
            self.client.upsert(
                collection_name=self.collection_name,
                points=[point]
            )

            logger.info(f"Upserted point to Qdrant: {point_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to upsert point {point_id}: {e}", exc_info=True)
            return False

    def upsert_batch(
        self,
        points_data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Batch upsert multiple points.

        Args:
            points_data: List of dicts with keys: point_id, embedding, payload

        Returns:
            Dict with success count and failed point IDs
        """
        if not points_data:
            return {"success": 0, "failed": []}

        # Ensure collection exists
        if not self.ensure_collection_exists():
            logger.error("Collection does not exist and failed to create")
            return {"success": 0, "failed": [p["point_id"] for p in points_data]}

        success_count = 0
        failed_ids = []

        try:
            # Prepare points
            points = []
            for data in points_data:
                try:
                    point = PointStruct(
                        id=data["point_id"],
                        vector=data["embedding"],
                        payload=data["payload"]
                    )
                    points.append(point)
                except Exception as e:
                    logger.error(f"Failed to prepare point {data.get('point_id')}: {e}")
                    failed_ids.append(data.get("point_id", "unknown"))

            # Batch upsert
            if points:
                self.client.upsert(
                    collection_name=self.collection_name,
                    points=points
                )
                success_count = len(points)
                logger.info(f"Batch upserted {success_count} points to Qdrant")

        except Exception as e:
            logger.error(f"Batch upsert failed: {e}", exc_info=True)
            # If batch fails, all points failed
            failed_ids.extend([p.id for p in points])
            success_count = 0

        return {
            "success": success_count,
            "failed": failed_ids
        }

    def delete_point(self, point_id: str) -> bool:
        """
        Delete a single point from Qdrant.

        Args:
            point_id: Point identifier to delete

        Returns:
            True if successful, False otherwise
        """
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=models.PointIdsList(
                    points=[point_id]
                )
            )
            logger.info(f"Deleted point from Qdrant: {point_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete point {point_id}: {e}", exc_info=True)
            return False

    def delete_batch(self, point_ids: List[str]) -> Dict[str, Any]:
        """
        Batch delete multiple points.

        Args:
            point_ids: List of point IDs to delete

        Returns:
            Dict with success count and failed point IDs
        """
        if not point_ids:
            return {"success": 0, "failed": []}

        success_count = 0
        failed_ids = []

        try:
            # Delete in batches of 100
            batch_size = 100
            for i in range(0, len(point_ids), batch_size):
                batch = point_ids[i:i + batch_size]
                try:
                    self.client.delete(
                        collection_name=self.collection_name,
                        points_selector=models.PointIdsList(points=batch)
                    )
                    success_count += len(batch)
                    logger.info(f"Deleted batch of {len(batch)} points from Qdrant")
                except Exception as e:
                    logger.error(f"Failed to delete batch {i//batch_size + 1}: {e}", exc_info=True)
                    # Try individual deletes for this batch
                    for point_id in batch:
                        try:
                            self.client.delete(
                                collection_name=self.collection_name,
                                points_selector=models.PointIdsList(points=[point_id])
                            )
                            success_count += 1
                        except Exception as individual_error:
                            logger.error(f"Failed to delete individual point {point_id}: {individual_error}")
                            failed_ids.append(point_id)

            logger.info(f"Batch deleted {success_count}/{len(point_ids)} points from Qdrant")

        except Exception as e:
            logger.error(f"Batch delete failed: {e}", exc_info=True)
            failed_ids = point_ids

        return {
            "success": success_count,
            "failed": failed_ids
        }

    def get_collection_info(self) -> Optional[Dict[str, Any]]:
        """
        Get collection information.

        Returns:
            Dict with collection stats or None
        """
        try:
            info = self.client.get_collection(collection_name=self.collection_name)

            # Extract points count from the collection info
            # The API returns points_count directly
            points_count = info.points_count if hasattr(info, 'points_count') else 0

            # vectors_count is deprecated, use points_count instead
            # Status is a string representation
            status_str = str(info.status) if hasattr(info, 'status') else "unknown"

            return {
                "name": self.collection_name,
                "vectors_count": points_count,  # Use points_count for backward compatibility
                "points_count": points_count,
                "status": status_str
            }
        except Exception as e:
            logger.error(f"Failed to get collection info: {e}", exc_info=True)
            return None

    def search_by_vector(
        self,
        query_vector: List[float],
        limit: int = 10,
        score_threshold: Optional[float] = None,
        filter_dict: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for similar vectors in Qdrant.

        Args:
            query_vector: Query embedding vector
            limit: Maximum number of results
            score_threshold: Minimum similarity score
            filter_dict: Metadata filter (e.g., {"category": "kitchen"})

        Returns:
            List of dicts with point_id, score, and payload
        """
        try:
            # Build filter if provided
            search_filter = None
            if filter_dict:
                from qdrant_client.models import Filter, FieldCondition, MatchValue
                conditions = []
                for key, value in filter_dict.items():
                    conditions.append(
                        FieldCondition(
                            key=key,
                            match=MatchValue(value=value)
                        )
                    )
                search_filter = Filter(must=conditions)

            # Perform search
            results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                limit=limit,
                score_threshold=score_threshold,
                query_filter=search_filter
            )

            # Format results
            formatted_results = []
            for result in results:
                formatted_results.append({
                    "point_id": result.id,
                    "score": result.score,
                    "payload": result.payload
                })

            logger.info(f"Search returned {len(formatted_results)} results")
            return formatted_results

        except Exception as e:
            logger.error(f"Search failed: {e}", exc_info=True)
            return []

    def scroll_points(
        self,
        limit: int = 100,
        offset: Optional[str] = None,
        filter_dict: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Scroll through points in collection (for listing).

        Args:
            limit: Number of points to retrieve
            offset: Offset for pagination
            filter_dict: Metadata filter

        Returns:
            Dict with points and next_offset
        """
        try:
            # Build filter if provided
            scroll_filter = None
            if filter_dict:
                from qdrant_client.models import Filter, FieldCondition, MatchValue
                conditions = []
                for key, value in filter_dict.items():
                    conditions.append(
                        FieldCondition(
                            key=key,
                            match=MatchValue(value=value)
                        )
                    )
                scroll_filter = Filter(must=conditions)

            # Scroll through points
            result = self.client.scroll(
                collection_name=self.collection_name,
                limit=limit,
                offset=offset,
                scroll_filter=scroll_filter,
                with_payload=True,
                with_vectors=False
            )

            points, next_offset = result

            # Format points
            formatted_points = []
            for point in points:
                formatted_points.append({
                    "point_id": point.id,
                    "payload": point.payload
                })

            return {
                "points": formatted_points,
                "next_offset": next_offset,
                "count": len(formatted_points)
            }

        except Exception as e:
            logger.error(f"Scroll failed: {e}", exc_info=True)
            return {"points": [], "next_offset": None, "count": 0}

    def update_point_payload(
        self,
        point_id: str,
        payload: Dict[str, Any]
    ) -> bool:
        """
        Update payload of an existing point without changing the vector.

        Args:
            point_id: Point identifier
            payload: New payload dictionary

        Returns:
            True if successful, False otherwise
        """
        try:
            self.client.set_payload(
                collection_name=self.collection_name,
                payload=payload,
                points=[point_id]
            )
            logger.info(f"Updated payload for point: {point_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to update payload for {point_id}: {e}", exc_info=True)
            return False

    def get_point(self, point_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a specific point by ID.

        Args:
            point_id: Point identifier

        Returns:
            Dict with point data or None
        """
        try:
            result = self.client.retrieve(
                collection_name=self.collection_name,
                ids=[point_id],
                with_payload=True,
                with_vectors=False
            )

            if result:
                point = result[0]
                return {
                    "point_id": point.id,
                    "payload": point.payload
                }
            return None

        except Exception as e:
            logger.error(f"Failed to get point {point_id}: {e}", exc_info=True)
            return None

    def health_check(self) -> bool:
        """
        Verify Qdrant service is accessible.

        Returns:
            True if service is healthy, False otherwise
        """
        try:
            # Try to get collections list
            collections = self.client.get_collections()
            logger.info(f"Qdrant health check passed: {len(collections.collections)} collections")
            return True
        except Exception as e:
            logger.error(f"Qdrant health check failed: {e}", exc_info=True)
            return False


# Singleton instance
qdrant_service = QdrantService()
