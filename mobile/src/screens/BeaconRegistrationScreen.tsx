import React, { useEffect, useState } from 'react';
import {
    View,
    Text,
    Button,
    FlatList,
    StyleSheet,
    ActivityIndicator,
    TextInput,
    Alert,
} from 'react-native';

import {scanForBeacons} from '../services/BleService';

import {
    loadRegisteredBeacons,
    registerBeacon,
    } from '../services/BeaconStore';

import * as BeaconApi from '../services/BeaconApi';


import { registerBeaconOnServer } from '../services/BeaconApi';

import type { BeaconReading } from '../types';
import type { RegisteredBeacon } from '../types/RegisteredBeacon';

console.log('BEACON API EXPORTS: ', Object.keys(BeaconApi));

const API_BASE = 'https://waypoint-backend.fly.dev'; // Replace with your backend server address

export default function BeaconRegistrationScreen() {
    const [beacons, setBeacons] = useState<BeaconReading[]>([]);
    const [registeredBeacons, setRegisteredBeacons] = useState<RegisteredBeacon[]>([]);

    const [roomName, setRoomName] = useState<Record<string, string>>({});

    const [scanning, setScanning] = useState(false);
    const [savingKey, setSavingKey] = useState<string | null>(null);

    const beaconKey = (beacon: {
        uuid: string;
        major: number;
        minor: number;
    }) =>
        `${beacon.uuid.toUpperCase()}-${beacon.major}-${beacon.minor}`;

    const refreshRegistered = async () => {
        const saved = await loadRegisteredBeacons();
        setRegisteredBeacons(saved);

        const names: Record<string, string> = {};

        saved.forEach((beacon) => {
            names[beaconKey(beacon)] = beacon.roomName || '';
        });

        setRoomName((previous) => ({
            ...previous,
            ...names,
        }));
    };

    useEffect(() => {
        refreshRegistered().catch((error) => {
            console.error('Failed to load registered beacons:', error);
        });
    }, []);

    const handleScan = async () => {
        setScanning(true);

        try {
            const found = await scanForBeacons();

            setBeacons(found);

            console.log('Found beacons:', found);
        } catch (error) {
            console.error('Error scanning for beacons:', error);

            Alert.alert('Error', 'Failed to scan for beacons. Please try again.');
        } finally {
            setScanning(false);
        }
    };

    const handleRegister = async (beacon: BeaconReading) => {

        if (!beacon.uuid) {
            Alert.alert(
                'Error',
                'Beacon UUID is missing. Cannot register this beacon.',
            );
            return;
        }

        const key = beaconKey(beacon);
        const name = (roomName[key] || '').trim();

        if (!name) {
            Alert.alert(
                'Error',
                'Room name is required to register a beacon.'
            );
            return;
        }

        setSavingKey(key);
        console.log('FUNCTION CHECK:', {
    registerBeaconOnServer: typeof registerBeaconOnServer,
    registerBeacon: typeof registerBeacon,
    loadRegisteredBeacons: typeof loadRegisteredBeacons,
});

        try {
            console.log('REGISTRATION API URL:', API_BASE);
            console.log('1. BEFORE SERVER');

            await registerBeaconOnServer(
                {
                uuid: beacon.uuid,
                major: beacon.major,
                minor: beacon.minor,
                room_name: name,
            }, API_BASE,);

            console.log('Beacon saved to server successfully. Now saving locally...');

            console.log('2. AFTER SERVER');

            await registerBeacon({
                uuid: beacon.uuid,
                major: beacon.major,
                minor: beacon.minor,
                roomName: name,
            });

            console.log('3. AFTER LOCAL SAVE');


            await refreshRegistered();

            console.log('4. AFTER REFRESH');

            Alert.alert(
                'Success',
                `${name} saved successfully.`,
            );
        } catch (error) {
            console.log(
                'Registration error:',
                error instanceof Error ? error.stack : String(error),
            );

        } finally {
            setSavingKey(null);
        }
};

const isRegistered = (beacon: BeaconReading): boolean => {
    return registeredBeacons.some(
        (item) => beaconKey(item) === beaconKey(beacon),
    );
};

return (
    <View style ={styles.container}>
        <Text style={styles.title}>Beacon Registration</Text>

        <Button
            title={scanning ? 'Scanning...' : 'Scan for Beacons'}
            onPress={handleScan}
            disabled={scanning || savingKey !== null}
            color = "#26A69A"
        />

        {scanning && (
            <View style={styles.loading}>
                <ActivityIndicator size="large" color="#26A69A" />

                <Text style={styles.text}>
                    Scanning for beacons...
                </Text>
            </View>
        )}

        <FlatList
            data={beacons}
            keyExtractor={beaconKey}
            keyboardShouldPersistTaps="handled"
            contentContainerStyle={styles.list}
            renderItem={({ item }) => {
                const key = beaconKey(item);
                const saved = isRegistered(item);
                const saving = savingKey === key;

                return (
                    <View style={styles.beacon}>
                        <Text style={styles.text}>
                            UUID: {item.uuid}
                        </Text>

                        <Text style={styles.text}>
                            Major: {item.major}, Minor: {item.minor}
                        </Text>

                        <Text style={styles.text}>
                            Minor: {item.minor}
                        </Text>

                        <Text style={styles.text}>
                            RSSI: {item.rssi}
                        </Text>

                        {saved && (
                            <Text style={styles.saved}>
                                Registered
                            </Text>
                        )}

                        <TextInput
                            style={styles.input}
                            placeholder="Enter room name"
                            placeholderTextColor="#AAAAAA"
                            value={roomName[key] || ''}
                            editable={!saving}
                            onChangeText={(value) =>
                                setRoomName((prev) => ({ ...prev, [key]: value }))
                            }
                        />

                        <Button
                            title={
                                saving ? 'Saving...' : saved ? 'Update Room' : 'Register Beacon'
                            }
                            onPress={() => handleRegister(item)}
                            disabled={savingKey !== null}
                            color = "#26A69A"
                        />

                        {saving && (
                            <ActivityIndicator
                                size="small"
                                color="#26A69A"
                                style={styles.savingIndicator}
                            />
                        )}
                        </View>
                );
            }}
            ListEmptyComponent={
                !scanning ? (
                    <Text style={styles.emptyText}>
                        No beacons found yet
                    </Text>
                ) : undefined
            }
        />
    </View>
);
}

const styles = StyleSheet.create({
    container: {
        flex: 1,
        padding: 20,
        backgroundColor: '#121212',
    },
    title: {
        fontSize: 24,
        fontWeight: 'bold',
        marginBottom: 20,
        color: '#FFFFFF'
    },
    beacon: {
        padding: 15,
        marginTop: 12,
        backgroundColor: '#242424',
        borderRadius: 10,
        borderWidth: 1,
        borderColor: '#444444'
    },
    text: {
        color: '#FFFFFF',
        fontSize: 16,
        marginBottom: 5,
    },
    saved: {
        color: '#4CAF50',
        fontSize: 16,
        fontWeight: 'bold',
        marginVertical: 8,
    },
    input: {
        backgroundColor: '#333333',
        color: '#FFFFFF',
        borderColor: '#666666',
        borderWidth: 1,
        borderRadius: 8,
        padding: 12,
        fontSize: 16,
        marginVertical: 12,
    },
    emptyText: {
        color: '#FFFFFF',
        fontSize: 16,
        textAlign: 'center',
        marginTop: 30,
    },
    loading: {
        alignItems: 'center',
        marginTop: 20,
    },
    savingIndicator: {
        marginTop: 10,
    },
    list: {
        paddingBottom: 30,
    },
});
