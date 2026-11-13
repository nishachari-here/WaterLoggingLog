#include <iostream>
#include <string>
#include <fstream>
#include <queue>
#include <unordered_map>
#include <unordered_set>
#include <vector>
#include <stdexcept>
#include <exception>
#include "json.hpp"

using json = nlohmann::json;

// Global data structures
std::unordered_map<std::string, std::vector<std::string>> adjacency;
std::unordered_map<std::string, int> zoneCapacity;
std::unordered_set<std::string> floodedZones;
std::queue<std::string> floodQueue;
std::vector<std::string> floodLog;

void loadZones(const std::string& filename) {
    std::ifstream file(filename);
    if (!file.is_open()) {
        throw std::runtime_error("Could not open zones.json");
    }

    json zonesData;
    file >> zonesData;

    for (const auto& zone : zonesData["zones"]) {
        std::string id = zone["id"];
        adjacency[id] = zone["adjacent"].get<std::vector<std::string>>();
        zoneCapacity[id] = zone["capacity"];
    }
}

void initFloodSimulation(const std::string& sourceZone) {
    // Clear previous state
    floodedZones.clear();
    while (!floodQueue.empty()) floodQueue.pop();
    floodLog.clear();

    // Initialize with source zone
    floodedZones.insert(sourceZone);
    floodQueue.push(sourceZone);
    floodLog.push_back("Flood started from " + sourceZone);
}

json performFloodStep() {
    json response;
    
    if (floodQueue.empty()) {
        response["status"] = "COMPLETE";
        response["message"] = "Flood simulation complete";
        response["flooded_zones"] = std::vector<std::string>(floodedZones.begin(), floodedZones.end());
        return response;
    }

    // BFS step: dequeue current zone
    std::string currentZone = floodQueue.front();
    floodQueue.pop();

    std::vector<std::string> newlyFlooded;

    // Process neighbors
    if (adjacency.find(currentZone) != adjacency.end()) {
        for (const std::string& neighbor : adjacency[currentZone]) {
            if (floodedZones.find(neighbor) == floodedZones.end()) {
                floodedZones.insert(neighbor);
                floodQueue.push(neighbor);
                newlyFlooded.push_back(neighbor);
                
                std::string logEntry = "Zone " + neighbor + " flooded from " + currentZone;
                floodLog.push_back(logEntry);
            }
        }
    }

    response["status"] = "OK";
    response["current_zone"] = currentZone;
    response["newly_flooded"] = newlyFlooded;
    response["flooded_zones"] = std::vector<std::string>(floodedZones.begin(), floodedZones.end());
    response["queue_size"] = floodQueue.size();
    response["log"] = floodLog;

    return response;
}

int main() {
    std::string input;
    bool zonesLoaded = false;

    // Main command loop
    while (std::getline(std::cin, input)) {
        try {
            json request = json::parse(input);
            std::string command = request["command"];

            json response;

            if (command == "PING") {
                response["status"] = "OK";
                response["message"] = "DSA Engine is alive";
            }
            else if (command == "INIT_SYSTEM") {
                try {
                    loadZones("data/zones.json");
                    zonesLoaded = true;
                    response["status"] = "READY";
                    response["zones_loaded"] = adjacency.size();
                    response["message"] = "System initialized successfully";
                } catch (const std::exception& e) {
                    response["status"] = "ERROR";
                    response["message"] = std::string("Failed to load zones: ") + e.what();
                }
            }
            else if (command == "START_FLOOD") {
                if (!zonesLoaded) {
                    response["status"] = "ERROR";
                    response["message"] = "System not initialized. Call INIT_SYSTEM first.";
                } else {
                    std::string sourceZone = request["source_zone"];
                    
                    // Validate source zone exists
                    if (adjacency.find(sourceZone) == adjacency.end()) {
                        response["status"] = "ERROR";
                        response["message"] = "Invalid source zone: " + sourceZone;
                    } else {
                        initFloodSimulation(sourceZone);
                        
                        response["status"] = "OK";
                        response["message"] = "Flood simulation started";
                        response["source_zone"] = sourceZone;
                        response["flooded_zones"] = std::vector<std::string>{sourceZone};
                    }
                }
            }
            else if (command == "FLOOD_STEP") {
                if (!zonesLoaded) {
                    response["status"] = "ERROR";
                    response["message"] = "System not initialized";
                } else {
                    response = performFloodStep();
                }
            }
            else if (command == "GET_FLOOD_STATE") {
                response["status"] = "OK";
                response["flooded_zones"] = std::vector<std::string>(floodedZones.begin(), floodedZones.end());
                response["queue_size"] = floodQueue.size();
                response["log"] = floodLog;
            }
            else {
                response["status"] = "ERROR";
                response["message"] = "Unknown command: " + command;
            }

            std::cout << response.dump() << std::endl;
            std::cout.flush();
        }
        catch (std::exception &e) {
            json error;
            error["status"] = "ERROR";
            error["message"] = e.what();
            std::cout << error.dump() << std::endl;
            std::cout.flush();
        }
    }

    return 0;
}
