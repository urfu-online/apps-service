// Backups Component
import React, { useState } from 'react';
import { Layout } from './layout/Layout';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getBackups, createBackup } from '../lib/api';
import { Backup } from '../lib/types';

export const Backups: React.FC = () => {
  const queryClient = useQueryClient();
  const [selectedService, setSelectedService] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [retentionDays, setRetentionDays] = useState(30);
  const [keepDaily, setKeepDaily] = useState(7);
  const [keepWeekly, setKeepWeekly] = useState(4);
  const [keepMonthly, setKeepMonthly] = useState(12);

  const {
    data: backups,
    isLoading,
    isError,
    error
  } = useQuery<Backup[]>({
    queryKey: ['backups', selectedService],
    queryFn: () => getBackups(selectedService),
    enabled: !!selectedService,
    staleTime: 5 * 60 * 1000, // 5 minutes
    cacheTime: 10 * 60 * 1000, // 10 minutes
  });

  const createBackupMutation = useMutation({
    mutationFn: (serviceName: string) => createBackup(serviceName),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['backups', selectedService] });
    },
  });

  const filteredBackups = backups?.filter(backup => {
    const matchesStatus = statusFilter === '' || backup.status === statusFilter;
    return matchesStatus;
  }) || [];

  const handleCreateBackup = (serviceName: string) => {
    createBackupMutation.mutate(serviceName);
  };

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
          <span className="block sm:inline">{error instanceof Error ? error.message : 'Failed to load backups'}</span>
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="bg-white shadow rounded-lg overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="text-xl font-semibold text-gray-800">Backups</h2>
        </div>
        
        <div className="p-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Service</label>
              <select
                className="w-full px-4 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={selectedService}
                onChange={(e) => setSelectedService(e.target.value)}
              >
                <option value="">Select a service</option>
                <option value="service-1">Service One</option>
                <option value="service-2">Service Two</option>
                <option value="service-3">Service Three</option>
              </select>
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Status</label>
              <select
                className="w-full px-4 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
              >
                <option value="">All Statuses</option>
                <option value="created">Created</option>
                <option value="uploading">Uploading</option>
                <option value="failed">Failed</option>
              </select>
            </div>
            
            <div className="flex items-end">
              <button 
                className="w-full px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                onClick={() => selectedService && handleCreateBackup(selectedService)}
                disabled={!selectedService}
              >
                {createBackupMutation.isLoading ? 'Creating...' : 'Create Backup'}
              </button>
            </div>
          </div>
          
          {selectedService && (
            <div className="mb-6">
              <h3 className="text-lg font-medium text-gray-900 mb-3">
                Backups for {selectedService} ({filteredBackups.length})
              </h3>
              
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">ID</th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Created</th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Size</th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Retention</th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200">
                    {filteredBackups.map((backup) => (
                      <tr key={backup.snapshot_id}>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="text-sm font-medium text-gray-900">{backup.snapshot_id.substring(0, 8)}...</div>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                          {new Date(backup.created_at).toLocaleString()}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <span className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full 
                            ${backup.status === 'created' ? 'bg-green-100 text-green-800' : 
                              backup.status === 'uploading' ? 'bg-yellow-100 text-yellow-800' : 
                              'bg-red-100 text-red-800'}`}>
                            {backup.status === 'created' ? 'Created' : 
                             backup.status === 'uploading' ? 'Uploading' : 'Failed'}
                          </span>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                          {(backup.size_bytes / 1024 / 1024).toFixed(2)} MB
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                          {backup.retention_days} days
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                          <button className="text-blue-600 hover:text-blue-900 mr-3">Restore</button>
                          <button className="text-red-600 hover:text-red-900">Delete</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              
              {filteredBackups.length === 0 && (
                <div className="text-center py-8">
                  <p className="text-gray-500">No backups found for this service</p>
                </div>
              )}
            </div>
          )}
          
          <div className="border-t border-gray-200 pt-6">
            <h3 className="text-lg font-medium text-gray-900 mb-3">Retention Policy Settings</h3>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Retention Days</label>
                <input
                  type="number"
                  className="w-full px-4 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={retentionDays}
                  onChange={(e) => setRetentionDays(Number(e.target.value))}
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Keep Daily</label>
                <input
                  type="number"
                  className="w-full px-4 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={keepDaily}
                  onChange={(e) => setKeepDaily(Number(e.target.value))}
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Keep Weekly</label>
                <input
                  type="number"
                  className="w-full px-4 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={keepWeekly}
                  onChange={(e) => setKeepWeekly(Number(e.target.value))}
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Keep Monthly</label>
                <input
                  type="number"
                  className="w-full px-4 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={keepMonthly}
                  onChange={(e) => setKeepMonthly(Number(e.target.value))}
                />
              </div>
            </div>
            
            <div className="mt-6">
              <label className="block text-sm font-medium text-gray-700 mb-1">Apply to Service</label>
              <select className="w-full px-4 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500">
                <option value="">Select a service</option>
                <option value="service-1">Service One</option>
                <option value="service-2">Service Two</option>
                <option value="service-3">Service Three</option>
              </select>
            </div>
            
            <div className="mt-6">
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500">
                Apply Retention Policy
              </button>
            </div>
          </div>
        </div>
      </div>
    </Layout>
  );
};