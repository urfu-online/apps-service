// Services Component
import React, { useEffect, useState } from 'react';
import { Layout } from './layout/Layout';
import { Service } from '../lib/types';
import { ServiceDetail } from './ServiceDetail';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getServices, deployService, stopService, restartService } from '../lib/api';

export const Services: React.FC = () => {
  const queryClient = useQueryClient();
  const [searchTerm, setSearchTerm] = useState('');
  const [visibilityFilter, setVisibilityFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [selectedService, setSelectedService] = useState<Service | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  
  const {
    data: services,
    isLoading,
    isError,
    error
  } = useQuery<Service[]>({
    queryKey: ['services'],
    queryFn: getServices,
    staleTime: 5 * 60 * 1000, // 5 minutes
    cacheTime: 10 * 60 * 1000, // 10 minutes
  });

  const deployMutation = useMutation({
    mutationFn: (serviceName: string) => deployService(serviceName),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['services'] });
      setActionError(null);
    },
    onError: (error) => {
      setActionError(`Failed to deploy service: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  });

  const stopMutation = useMutation({
    mutationFn: (serviceName: string) => stopService(serviceName),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['services'] });
      setActionError(null);
    },
    onError: (error) => {
      setActionError(`Failed to stop service: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  });

  const restartMutation = useMutation({
    mutationFn: (serviceName: string) => restartService(serviceName),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['services'] });
      setActionError(null);
    },
    onError: (error) => {
      setActionError(`Failed to restart service: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  });

  const filteredServices = services?.filter(service => {
    const matchesSearch = 
      service.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (service.display_name && service.display_name.toLowerCase().includes(searchTerm.toLowerCase()));
    
    const matchesVisibility = visibilityFilter === 'all' || service.visibility === visibilityFilter;
    const matchesStatus = statusFilter === 'all' || service.status === statusFilter;
    
    return matchesSearch && matchesVisibility && matchesStatus;
  }) || [];

  const handleViewService = (service: Service) => {
    setSelectedService(service);
  };

  const handleCloseModal = () => {
    setSelectedService(null);
  };

  const handleDeploy = (serviceName: string) => {
    deployMutation.mutate(serviceName);
  };

  const handleStop = (serviceName: string) => {
    stopMutation.mutate(serviceName);
  };

  const handleRestart = (serviceName: string) => {
    restartMutation.mutate(serviceName);
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
          <span className="block sm:inline">{error instanceof Error ? error.message : 'Failed to load services'}</span>
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="bg-white shadow rounded-lg overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200 flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <h2 className="text-xl font-semibold text-gray-800">Services</h2>
          
          <div className="flex flex-col md:flex-row gap-3 w-full md:w-auto">
            <input
              type="text"
              placeholder="Search services..."
              className="px-4 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
            
            <select
              className="px-4 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={visibilityFilter}
              onChange={(e) => setVisibilityFilter(e.target.value)}
            >
              <option value="all">All Visibility</option>
              <option value="public">Public</option>
              <option value="internal">Internal</option>
            </select>
            
            <select
              className="px-4 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="all">All Status</option>
              <option value="running">Running</option>
              <option value="stopped">Stopped</option>
              <option value="partial">Partial</option>
            </select>
            
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500">
              Apply Filters
            </button>
          </div>
        </div>
        
        {actionError && (
          <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 mx-4 mt-4 rounded relative" role="alert">
            <strong className="font-bold">Error! </strong>
            <span className="block sm:inline">{actionError}</span>
          </div>
        )}
        
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Name</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Version</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Visibility</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Routing</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {filteredServices.map((service) => (
                <tr key={service.name}>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm font-medium text-gray-900">{service.display_name || service.name}</div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm text-gray-900">{service.version || '-'}</div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full 
                      ${service.visibility === 'public' ? 'bg-blue-100 text-blue-800' : 'bg-gray-100 text-gray-800'}`}>
                      {service.visibility}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full 
                      ${service.status === 'running' ? 'bg-green-100 text-green-800' : 
                        service.status === 'stopped' ? 'bg-red-100 text-red-800' : 
                        'bg-yellow-100 text-yellow-800'}`}>
                      {service.status === 'running' ? 'Running' : 
                       service.status === 'stopped' ? 'Stopped' : 'Partial'}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {service.routing?.map((route, index) => (
                      <div key={index}>
                        {route.type === 'domain' && `🌐 ${route.domain}`}
                        {route.type === 'port' && `🔌 :${route.port}`}
                        {route.type === 'subfolder' && `📁 ${route.base_domain}${route.path}`}
                      </div>
                    )) || '-'}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                    <button 
                      className="text-blue-600 hover:text-blue-900 mr-3"
                      onClick={() => handleViewService(service)}
                    >
                      View
                    </button>
                    <button 
                      className="text-green-600 hover:text-green-900 mr-3"
                      onClick={() => handleRestart(service.name)}
                      disabled={restartMutation.isLoading}
                    >
                      {restartMutation.isLoading ? 'Restarting...' : 'Restart'}
                    </button>
                    <button 
                      className="text-red-600 hover:text-red-900"
                      onClick={() => handleStop(service.name)}
                      disabled={stopMutation.isLoading}
                    >
                      {stopMutation.isLoading ? 'Stopping...' : 'Stop'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        
        {filteredServices.length === 0 && (
          <div className="text-center py-8">
            <p className="text-gray-500">No services found matching your criteria</p>
          </div>
        )}
      </div>
      
      {selectedService && (
        <ServiceDetail 
          service={selectedService} 
          onClose={handleCloseModal} 
        />
      )}
    </Layout>
  );
};