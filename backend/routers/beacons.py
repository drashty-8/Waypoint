import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from database import supabase
from routers.photos import PLACEHOLDER_USER_ID

router = APIRouter(prefix="/beacons", tags=["beacons"])

logger = logging.getLogger(__name__)

class BeaconRegistration(BaseModel):
    uuid: UUID = Field(
        ...,
        description="The UUID of the beacon")
    major: int = Field(
        ...,
        description="The major value of the beacon")
    minor: int = Field(
        ...,
        description="The minor value of the beacon")
    room_name: str = Field(
        ...,
        description="The name of the room associated with the beacon")

@router.post("", status_code=201)
async def register_beacon(beacon: BeaconRegistration):
    room_name = beacon.room_name.strip()

    if not room_name:
        raise HTTPException(
            status_code=400,
            detail="Room name cannot be empty"
        )
    # Check if the beacon already exists
    existing = (
        supabase.table("beacons")
        .select("id")
        .eq("user_id", PLACEHOLDER_USER_ID)
        .eq("beacon_uuid", str(beacon.uuid))
        .eq("major", beacon.major)
        .eq("minor", beacon.minor)
        .execute()
    )

    if existing.data:
        beacon_id = existing.data[0]["id"]

        result = (
            supabase.table("beacons")
            .update({"room_name": room_name})
            .eq("id", beacon_id)
            .eq("user_id", PLACEHOLDER_USER_ID)
            .execute()
        )

        if not result.data:
            raise HTTPException(
                status_code=500,
                detail="Could not update beacon"
            )

        logger.info("Updated beacon %s", beacon_id)

        return {
            "message": "Beacon room updated successfully",
            "beacon": result.data[0]
        }

    result = (
        supabase.table("beacons")
        .insert ({
            "beacon_uuid": str(beacon.uuid),
            "major": beacon.major,
            "minor": beacon.minor,
            "room_name": room_name,
            "user_id": PLACEHOLDER_USER_ID
            })
            .execute()
        )

    if not result.data:
        raise HTTPException(
            status_code=500,
            detail="Could not register Beacon"
        )

    logger.info(
        "Registered beacon %s / %s / %s",
        beacon.uuid,
        beacon.major,
        beacon.minor
    )

    return {
        "message": "Beacon registered successfully",
        "beacon": result.data[0]
    }