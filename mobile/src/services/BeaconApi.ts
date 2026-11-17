export type BeaconRegistationPayload = {
    uuid: string;
    major: number;
    minor: number;
    room_name: string;
};

export async function registerBeaconOnServer(
    beacon: BeaconRegistationPayload,
    apiBase: string
): Promise<void> {
    const response = await fetch(`${apiBase}/beacons`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
    },
    body: JSON.stringify(beacon),
});

    if (!response.ok) {
    const errorText = await response.text();

    throw new Error(`Failed to register beacon on server: ${response.status} ${errorText}`);
    }
}