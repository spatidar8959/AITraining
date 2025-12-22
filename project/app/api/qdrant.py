"""
Qdrant/Vector Database Management API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional, List
import os

from app.database import get_db
from app.models import ExtractedFrame, FrameEmbedding, VideoBatch, FrameStatus
from app.schemas import (
    QdrantPointSearchRequest,
    QdrantSearchResponse,
    QdrantCollectionInfoResponse,
    QdrantPointDeleteRequest,
    QdrantPointDeleteResponse,
    QdrantPointResponse
)
from app.services.qdrant_service import qdrant_service
from app.services.embedding_service import embedding_service
from app.services.s3_service import s3_service
from app.utils.logger import app_logger

router = APIRouter(prefix="/api/qdrant", tags=["qdrant"])


@router.get("/collection/info", response_model=QdrantCollectionInfoResponse)
async def get_collection_info():
    """
    Get Qdrant collection information.

    Returns:
        Collection statistics (vectors count, points count, status)
    """
    try:
        info = qdrant_service.get_collection_info()
        if not info:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve collection info"
            )

        return QdrantCollectionInfoResponse(
            collection_name=info["name"],
            vectors_count=info["vectors_count"],
            points_count=info["points_count"],
            status=info["status"]
        )

    except HTTPException:
        raise
    except Exception as e:
        app_logger.error(f"Error getting collection info: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get collection info: {str(e)}"
        )


@router.get("/points/list", response_model=QdrantSearchResponse)
async def list_points(
    limit: int = Query(50, ge=1, le=1000, description="Number of points to retrieve"),
    offset: Optional[str] = Query(None, description="Offset for pagination"),
    category: Optional[str] = Query(None, description="Filter by category"),
    db: Session = Depends(get_db)
):
    """
    List all points in Qdrant collection with pagination.

    Args:
        limit: Number of points to retrieve
        offset: Pagination offset
        category: Filter by category
        db: Database session

    Returns:
        List of points with payloads
    """
    try:
        # Build filter
        filter_dict = {}
        if category:
            filter_dict["category"] = category

        # Scroll through points
        result = qdrant_service.scroll_points(
            limit=limit,
            offset=offset,
            filter_dict=filter_dict if filter_dict else None
        )

        # Format response
        points = [
            QdrantPointResponse(
                point_id=point["point_id"],
                score=None,
                payload=point["payload"]
            )
            for point in result["points"]
        ]

        return QdrantSearchResponse(
            results=points,
            total=result["count"]
        )

    except Exception as e:
        app_logger.error(f"Error listing points: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list points: {str(e)}"
        )


@router.post("/search", response_model=QdrantSearchResponse)
async def search_points(
    request: QdrantPointSearchRequest,
    db: Session = Depends(get_db)
):
    """
    Search for similar vectors in Qdrant.

    Supports:
    - Text query (generates embedding from text)
    - Image query (generates embedding from S3 image path)
    - Category filtering
    - Score threshold

    Args:
        request: Search parameters
        db: Database session

    Returns:
        List of similar points with scores
    """
    try:
        query_vector = None

        # Generate embedding from text query
        if request.query_text:
            # For text search, we need a text embedding model
            # Since we only have image embedding, return error
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Text search not supported. Use query_image_path instead."
            )

        # Generate embedding from image
        elif request.query_image_path:
            # Check if it's an S3 path or local path
            if request.query_image_path.startswith('frames/'):
                # Download from S3
                try:
                    image_bytes = s3_service.download_file_to_memory(request.query_image_path)

                    # Save temporarily
                    temp_path = f"/tmp/query_image_{os.urandom(8).hex()}.jpg"
                    with open(temp_path, 'wb') as f:
                        f.write(image_bytes)

                    # Generate embedding
                    query_vector = embedding_service.generate_embedding(temp_path)

                    # Clean up
                    os.remove(temp_path)

                except Exception as e:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Failed to process image: {str(e)}"
                    )
            else:
                # Assume it's a frame ID
                try:
                    frame_id = int(request.query_image_path)

                    # Get embedding from database
                    embedding_record = db.query(FrameEmbedding).filter(
                        FrameEmbedding.frame_id == frame_id
                    ).first()

                    if not embedding_record:
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Embedding not found for frame {frame_id}"
                        )

                    query_vector = embedding_record.embedding

                except ValueError:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="query_image_path must be S3 path or frame ID"
                    )

        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either query_text or query_image_path must be provided"
            )

        # Build filter
        filter_dict = {}
        if request.filter_category:
            filter_dict["category"] = request.filter_category

        # Perform search
        results = qdrant_service.search_by_vector(
            query_vector=query_vector,
            limit=request.limit,
            score_threshold=request.score_threshold,
            filter_dict=filter_dict if filter_dict else None
        )

        # Format response
        points = [
            QdrantPointResponse(
                point_id=result["point_id"],
                score=result["score"],
                payload=result["payload"]
            )
            for result in results
        ]

        return QdrantSearchResponse(
            results=points,
            total=len(points)
        )

    except HTTPException:
        raise
    except Exception as e:
        app_logger.error(f"Error searching points: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}"
        )


@router.delete("/points", response_model=QdrantPointDeleteResponse)
async def delete_points(
    request: QdrantPointDeleteRequest,
    db: Session = Depends(get_db)
):
    """
    Delete specific points from Qdrant by point IDs.

    Also updates corresponding frames in database to mark as not trained.

    Args:
        request: List of point IDs to delete
        db: Database session

    Returns:
        Deletion summary
    """
    try:
        # Delete from Qdrant
        result = qdrant_service.delete_batch(request.point_ids)

        # Update frames in database
        frames_updated = 0
        for point_id in request.point_ids:
            frame = db.query(ExtractedFrame).filter(
                ExtractedFrame.qdrant_point_id == point_id
            ).first()

            if frame:
                frame.status = FrameStatus.SELECTED
                frame.qdrant_point_id = None
                frames_updated += 1

        db.commit()

        app_logger.info(
            f"Deleted {result['success']} points from Qdrant, "
            f"updated {frames_updated} frames in database"
        )

        return QdrantPointDeleteResponse(
            deleted_count=result["success"],
            message=f"Deleted {result['success']} points, updated {frames_updated} frames"
        )

    except Exception as e:
        app_logger.error(f"Error deleting points: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete points: {str(e)}"
        )


@router.get("/point/{point_id}", response_model=QdrantPointResponse)
async def get_point_detail(point_id: str):
    """
    Get details of a specific point by ID.

    Args:
        point_id: Point identifier

    Returns:
        Point with payload
    """
    try:
        point = qdrant_service.get_point(point_id)
        if not point:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Point {point_id} not found"
            )

        return QdrantPointResponse(
            point_id=point["point_id"],
            score=None,
            payload=point["payload"]
        )

    except HTTPException:
        raise
    except Exception as e:
        app_logger.error(f"Error getting point: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get point: {str(e)}"
        )
