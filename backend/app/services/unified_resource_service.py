"""
Unified Resource Management Service

This service provides a single source of truth for resource management,
unifying the resources and available_resources systems. It ensures that
every resource has a provider_id, location_id, and status, and maintains
consistency between the two tables via database triggers.

The service provides methods for:
- Creating resources (both direct and via inventory)
- Updating resource status and quantities
- Querying unified resources
- Managing resource allocations
"""

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.database import db
from app.schemas import ResourceCreate, ResourceStatus
from app.services.allocation_engine import AvailableResource, PriorityWeights, ResourceNeed, solve_allocation

logger = logging.getLogger(__name__)


class UnifiedResourceService:
    """Service for unified resource management across resources and available_resources tables."""

    def __init__(self):
        pass

    async def create_resource(
        self, resource_data: ResourceCreate, provider_id: UUID, location_id: UUID, user_role: str = "ngo"
    ) -> dict[str, Any]:
        """
        Create a new resource entry in the resources table.
        This will automatically trigger the database trigger to update available_resources.

        Args:
            resource_data: Resource creation data
            provider_id: ID of the provider (NGO, donor, etc.)
            location_id: ID of the location where resource is stored
            user_role: Role of the user creating the resource

        Returns:
            Created resource data
        """
        try:
            # Prepare resource data
            resource_dict = resource_data.model_dump()
            resource_dict["provider_id"] = str(provider_id)
            resource_dict["location_id"] = str(location_id)
            resource_dict["status"] = ResourceStatus.AVAILABLE.value
            resource_dict["created_at"] = datetime.now(UTC).isoformat()
            resource_dict["updated_at"] = datetime.now(UTC).isoformat()

            # Insert into resources table
            response = await db.table("resources").insert(resource_dict).async_execute()

            if not response.data:
                raise Exception("Failed to create resource")

            created_resource = response.data[0]
            logger.info(f"Resource created: {created_resource['id']} by {user_role} {provider_id}")

            return created_resource

        except Exception as e:
            logger.error(f"Error creating resource: {str(e)}")
            raise

    async def create_inventory_item(
        self,
        provider_id: UUID,
        category: str,
        resource_type: str,
        title: str,
        description: str,
        total_quantity: int,
        unit: str = "units",
        address_text: str = "",
        location_id: UUID | None = None,
        user_role: str = "ngo",
        sku: str | None = None,
        min_stock_level: int = 5,
        reorder_point: int = 10,
        item_condition: str = "new",
        storage_requirements: dict | None = None,
        internal_location: str | None = None,
    ) -> dict[str, Any]:
        """
        Create an inventory item in available_resources table.
        This will also create corresponding entries in the resources table.

        Args:
            provider_id: ID of the provider
            category: Resource category (Food, Water, Medical, etc.)
            resource_type: Specific resource type
            title: Resource title
            description: Resource description
            total_quantity: Total quantity available
            unit: Unit of measurement
            address_text: Address text for the resource
            location_id: Optional location ID
            user_role: Role of the user creating the item
            sku: Optional barcode/SKU
            min_stock_level: Threshold for low stock alerts
            reorder_point: Recommended stock level for reordering
            item_condition: Condition of the item (new, used, etc.)
            storage_requirements: JSON dict of storage needs
            internal_location: Shelf/Bin identifier

        Returns:
            Created inventory item data
        """
        try:
            # First create the available_resources entry
            inventory_data = {
                "provider_id": str(provider_id),
                "provider_role": user_role,
                "category": category,
                "resource_type": resource_type,
                "title": title,
                "description": description,
                "total_quantity": total_quantity,
                "claimed_quantity": 0,
                "unit": unit,
                "address_text": address_text,
                "status": "available",
                "is_active": True,
                "sku": sku,
                "min_stock_level": min_stock_level,
                "reorder_point": reorder_point,
                "item_condition": item_condition,
                "storage_requirements": storage_requirements or {},
                "internal_location": internal_location,
                "created_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
            }

            # Filter out keys not supported by database schema to prevent errors
            # if migrations haven't been run yet.
            db_cols = [
                "resource_id", "provider_id", "provider_role", "category",
                "resource_type", "title", "description", "total_quantity",
                "claimed_quantity", "is_active", "status", "address_text",
                "location_lat", "location_long", "expiry_at", "created_at",
                "updated_at", "unit"
            ]
            insert_data = {k: v for k, v in inventory_data.items() if k in db_cols}

            response = await db.table("available_resources").insert(insert_data).async_execute()

            if not response.data:
                raise Exception("Failed to create inventory item")

            created_item = response.data[0]

            # Create corresponding resource entries
            resource_data = {
                "provider_id": str(provider_id),
                "location_id": str(location_id) if location_id else None,
                "type": self._map_category_to_resource_type(category),
                "name": title,
                "description": description,
                "quantity": total_quantity,
                "unit": unit,
                "status": "available",
                "priority": 5,
                "quality_status": "good" if item_condition == "new" else "fair",
                "tags": [category.lower(), item_condition],
                "created_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
            }

            # Filter out keys not supported by database schema
            res_db_cols = [
                "id", "provider_id", "location_id", "type", "name",
                "description", "quantity", "unit", "status", "priority",
                "availability_status", "expiry_date", "created_at", "updated_at"
            ]
            final_res_data = {k: v for k, v in resource_data.items() if k in res_db_cols}

            resource_response = await db.table("resources").insert(final_res_data).async_execute()

            if not resource_response.data:
                # Rollback the available_resources entry if resource creation fails
                await (
                    db.table("available_resources")
                    .delete()
                    .eq("resource_id", created_item["resource_id"])
                    .async_execute()
                )
                raise Exception("Failed to create corresponding resource entry")

            logger.info(f"Inventory item created: {created_item['resource_id']} by {user_role} {provider_id}")

            return created_item

        except Exception as e:
            logger.error(f"Error creating inventory item: {str(e)}")
            raise

    async def update_resource_status(
        self, resource_id: str, status: ResourceStatus, disaster_id: str | None = None
    ) -> dict[str, Any]:
        """
        Update the status of a resource and optionally assign it to a disaster.
        This will trigger the database trigger to update available_resources.

        Args:
            resource_id: ID of the resource to update
            status: New status for the resource
            disaster_id: Optional disaster ID to assign the resource to

        Returns:
            Updated resource data
        """
        try:
            status_val = status.value if hasattr(status, "value") else status
            update_data = {
                "status": status_val,
                "disaster_id": disaster_id,
                "updated_at": datetime.now(UTC).isoformat(),
            }

            response = await db.table("resources").update(update_data).eq("id", resource_id).async_execute()

            if not response.data:
                raise Exception("Failed to update resource status")

            updated_resource = response.data[0]
            status_val = status.value if hasattr(status, "value") else status
            logger.info(f"Resource status updated: {resource_id} -> {status_val}")

            return updated_resource

        except Exception as e:
            logger.error(f"Error updating resource status: {str(e)}")
            raise

    async def deallocate_resource(self, resource_id: str) -> dict[str, Any]:
        """
        Deallocate a resource and make it available again.
        This will trigger the database trigger to update available_resources.

        Args:
            resource_id: ID of the resource to deallocate

        Returns:
            Updated resource data
        """
        try:
            update_data = {
                "status": ResourceStatus.AVAILABLE.value,
                "disaster_id": None,
                "allocated_to": None,
                "updated_at": datetime.now(UTC).isoformat(),
            }

            response = await db.table("resources").update(update_data).eq("id", resource_id).async_execute()

            if not response.data:
                raise Exception("Failed to deallocate resource")

            updated_resource = response.data[0]
            logger.info(f"Resource deallocated: {resource_id}")

            return updated_resource

        except Exception as e:
            logger.error(f"Error deallocating resource: {str(e)}")
            raise

    async def get_unified_resources(
        self,
        provider_id: UUID | None = None,
        category: str | None = None,
        status: ResourceStatus | None = None,
        disaster_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """
        Get unified resources from the vw_unified_resources view.
        This provides a single source of truth combining both tables.

        Args:
            provider_id: Filter by provider ID
            category: Filter by resource category
            status: Filter by resource status
            disaster_id: Filter by disaster ID
            limit: Number of results to return
            offset: Offset for pagination

        Returns:
            Dictionary with resources list, total count, and category summary
        """
        try:
            query = db.table("vw_unified_resources").select("*")

            if provider_id:
                query = query.eq("provider_id", str(provider_id))
            if category:
                query = query.eq("category", category)
            if status:
                status_val = status.value if hasattr(status, "value") else status
                query = query.eq("status", status_val)
            if disaster_id:
                # Note: disaster_id filtering would need to be added to the view
                # For now, we'll filter in the resources table separately
                pass

            query = query.order("updated_at", desc=True).range(offset, offset + limit - 1)
            response = await query.async_execute()

            resources = response.data or []

            # Get total count
            count_query = db.table("vw_unified_resources").select("resource_id", count="exact")
            if provider_id:
                count_query = count_query.eq("provider_id", str(provider_id))
            if category:
                count_query = count_query.eq("category", category)
            if status:
                status_val = status.value if hasattr(status, "value") else status
                count_query = count_query.eq("status", status_val)

            count_response = await count_query.async_execute()
            total = count_response.count or 0

            # Get category summary
            category_query = db.table("vw_unified_resources").select("category, total_quantity, claimed_quantity")
            if provider_id:
                category_query = category_query.eq("provider_id", str(provider_id))

            category_response = await category_query.async_execute()
            category_data = category_response.data or []

            category_summary = {}
            for row in category_data:
                cat = row.get("category", "Unknown")
                if cat not in category_summary:
                    category_summary[cat] = {"total": 0, "claimed": 0, "count": 0}
                category_summary[cat]["total"] += row.get("total_quantity", 0) or 0
                category_summary[cat]["claimed"] += row.get("claimed_quantity", 0) or 0
                category_summary[cat]["count"] += 1

            return {"resources": resources, "total": total, "category_summary": category_summary}

        except Exception as e:
            logger.error(f"Error getting unified resources: {str(e)}")
            raise

    async def allocate_resources(
        self,
        disaster_id: str,
        required_resources: list[dict[str, Any]],
        max_distance_km: float = 500.0,
        priority_weights: PriorityWeights | None = None,
    ) -> dict[str, Any]:
        """
        Allocate resources to a disaster using the allocation engine.
        Only considers resources with status = 'available'.

        Args:
            disaster_id: ID of the disaster to allocate resources to
            required_resources: List of required resources
            max_distance_km: Maximum distance for resource allocation
            priority_weights: Priority weights for allocation algorithm

        Returns:
            Allocation result with allocations, unmet needs, and scores
        """
        try:
            # Get available resources from the unified view
            resources_response = await self.get_unified_resources(status=ResourceStatus.AVAILABLE)
            available_resources_data = resources_response["resources"]

            # Convert to AvailableResource objects for the allocation engine
            available_resources = []
            for r in available_resources_data:
                # Get location coordinates
                location_coords = await self._get_location_coordinates(r.get("location_id"))
                lat, lng = location_coords if location_coords else (0.0, 0.0)

                available_resources.append(
                    AvailableResource(
                        id=r["resource_id"],
                        resource_type=r["resource_type"],
                        quantity=r.get("remaining_quantity", 0),
                        priority=r.get("priority", 5),
                        location_lat=lat,
                        location_lng=lng,
                        location_id=r.get("location_id", ""),
                        expiry_date=None,  # Could be added if needed
                    )
                )

            # Convert required resources to ResourceNeed objects
            needs = []
            for req in required_resources:
                needs.append(
                    ResourceNeed(
                        need_type=req["type"],
                        quantity=req["quantity"],
                        urgency=req.get("priority", 5),
                        zone_lat=0.0,  # Would need disaster location
                        zone_lng=0.0,
                    )
                )

            # Run allocation algorithm
            result = solve_allocation(
                resources=available_resources, needs=needs, weights=priority_weights, max_distance_km=max_distance_km
            )

            # Update resource statuses for allocated resources
            allocated_ids = [alloc["resource_id"] for alloc in result.allocations]
            if allocated_ids:
                await (
                    db.table("resources")
                    .update(
                        {
                            "status": ResourceStatus.ALLOCATED.value,
                            "disaster_id": disaster_id,
                            "updated_at": datetime.now(UTC).isoformat(),
                        }
                    )
                    .in_("id", allocated_ids)
                    .async_execute()
                )

            return {
                "disaster_id": disaster_id,
                "allocations": result.allocations,
                "optimization_score": result.optimization_score,
                "unmet_needs": result.unmet_needs,
                "score_breakdown": {
                    "coverage_pct": result.coverage_pct,
                    "unmet_needs": result.unmet_needs,
                    "estimated_delivery_km": result.estimated_delivery_km,
                    "solver_status": result.solver_status,
                },
            }

        except Exception as e:
            logger.error(f"Error allocating resources: {str(e)}")
            raise

    async def get_resource_by_id(self, resource_id: str) -> dict[str, Any] | None:
        """Get a specific resource by ID from the unified view."""
        try:
            response = (
                await db.table("vw_unified_resources")
                .select("*")
                .eq("resource_id", resource_id)
                .single()
                .async_execute()
            )
            return response.data if response.data else None
        except Exception as e:
            logger.error(f"Error getting resource by ID: {str(e)}")
            return None

    async def _get_location_coordinates(self, location_id: str | None) -> tuple | None:
        """Get latitude and longitude for a location ID."""
        if not location_id:
            return None

        try:
            response = (
                await db.table("locations").select("latitude, longitude").eq("id", location_id).single().async_execute()
            )
            if response.data:
                return (response.data["latitude"], response.data["longitude"])
            return None
        except Exception:
            return None

    def _map_category_to_resource_type(self, category: str) -> str:
        """Map category to resource type for the resources table."""
        mapping = {
            "Food": "food",
            "Water": "water",
            "Medical": "medical",
            "Shelter": "shelter",
            "Volunteers": "personnel",
            "Equipment": "equipment",
        }
        return mapping.get(category, "other")


# Global instance of the service
unified_resource_service = UnifiedResourceService()
