// Logs Component
import React, { useState, useEffect } from 'react';
import { Layout } from './layout/Layout';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { getLogs } from '../lib/api';
import { LogEntry } from '../lib/types';

export const Logs: React.FC = () => {
  const queryClient = useQueryClient();
  const [searchTerm, setSearchTerm] = useState('');
  const [timeRange, setTimeRange] = useState('1h');
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [selectedService, setSelectedService] = useState<string>('');

  const {
    data: logs,
    isLoading,
    isError,
    error
  } = useQuery<LogEntry[]>({
    queryKey: ['logs', selectedService],
    queryFn: () => getLogs(selectedService),
    enabled: !!selectedService,
    staleTime: 5 * 60 * 1000, // 5 minutes
    cacheTime: 10 * 60 * 1000, // 10 minutes
  });

  // Set up auto-refresh if enabled
  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (autoRefresh && selectedService) {
      interval = setInterval(() => {
        queryClient.invalidateQueries({ queryKey: ['logs', selectedService, timeRange] });
      }, 5000);
    }
    
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [autoRefresh, selectedService, timeRange, queryClient]);

  const filteredLogs = logs?.filter(log => 
    log.message.toLowerCase().includes(searchTerm.toLowerCase())
  ) || [];

  if (isLoading) {
    return (
      <Layout>
        <div className="flex justify-center items-center h-64">
          <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500"></div>
        </div>
      </Layout>
    );
  }

  if (isError) {
    return (
      <Layout>
        <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded relative" role="alert">
          <strong className="font-bold">Error! </strong>
          <span className="block sm:inline">{error instanceof Error ? error.message : 'Failed to load logs'}</span>
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="bg-white shadow rounded-lg overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200 flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <h2 className="text-xl font-semibold text-gray-800">Logs</h2>
          
          <div className="flex flex-col md:flex-row gap-3 w-full md:w-auto">
            <select
              className="px-4 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={selectedService}
              onChange={(e) => setSelectedService(e.target.value)}
            >
              <option value="">Select a service</option>
              <option value="service-1">Service One</option>
              <option value="service-2">Service Two</option>
              <option value="service-3">Service Three</option>
            </select>
            
            <input
              type="text"
              placeholder="Search logs..."
              className="px-4 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
            
            <select
              className="px-4 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={timeRange}
              onChange={(e) => setTimeRange(e.target.value)}
            >
              <option value="1h">Last 1 hour</option>
              <option value="6h">Last 6 hours</option>
              <option value="12h">Last 12 hours</option>
              <option value="24h">Last 24 hours</option>
              <option value="7d">Last 7 days</option>
            </select>
            
            <div className="flex items-center">
              <input
                type="checkbox"
                id="autoRefresh"
                className="mr-2"
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
              />
              <label htmlFor="autoRefresh" className="text-sm">Auto-refresh</label>
            </div>
            
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500">
              Load Logs
            </button>
            
            <button className="px-4 py-2 bg-green-500 text-white rounded-md hover:bg-green-600 focus:outline-none focus:ring-2 focus:ring-green-500">
              Export Logs
            </button>
          </div>
        </div>
        
        <div className="p-4">
          {selectedService ? (
            <>
              <div className="font-mono text-sm bg-gray-100 rounded p-4 h-96 overflow-y-auto">
                {filteredLogs.map((log, index) => (
                  <div key={index} className="mb-1">
                    <span className="text-gray-500">{new Date(log.timestamp).toLocaleString()}</span>
                    <span className={`ml-2 ${log.level === 'error' ? 'text-red-600' : log.level === 'warn' ? 'text-yellow-600' : 'text-blue-600'}`}>
                      [{log.level.toUpperCase()}]
                    </span>
                    <span className="ml-2">{log.message}</span>
                  </div>
                ))}
              </div>
              
              {filteredLogs.length === 0 && (
                <div className="text-center py-8">
                  <p className="text-gray-500">No logs found for this service</p>
                </div>
              )}
            </>
          ) : (
            <div className="text-center py-8">
              <p className="text-gray-500">Please select a service to view logs</p>
            </div>
          )}
        </div>
      </div>
    </Layout>
  );
};