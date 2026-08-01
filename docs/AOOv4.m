function [Best_Score,Best_X,convergence_curve]= AOOv4(pop_size,iter_max,lb,ub,dim,fhd,varargin)
%% 初始化 (signature standardized: pop_size, iter_max, lb, ub, dim, fhd, varargin)


Best_Score=inf;
convergence_curve=zeros(iter_max,1);


x = 3 * rand(1, pop_size) / dim;
m = 0.5 * rand(1, pop_size) / dim;
L = pop_size / dim * rand(1, pop_size);
e = m;
g = 9.8/dim;    



X=initialization(pop_size,dim,ub,lb);

Pop_Fit = feval(fhd,X',varargin{:});
for i = 1:pop_size
    if Pop_Fit(i)<Best_Score
        Best_Score=Pop_Fit(i);
        Best_X=X(i,:);
    end
end
convergence_curve(1) = Best_Score;

%%迭代部分

for t = 2 :1:iter_max
    theta = pi * rand(1,pop_size);
    c = (1 -  t / iter_max)^3;
    P = Levy(pop_size,dim,1.5);

    for i = 1 :pop_size
        if rand > 0.5
            W = c/pi *(2 * rand(1,dim) - 1) .* ub  ;
            if mod(i,pop_size/10) == 0
                X(i,:) = mean(X) + W;
            elseif mod(i,pop_size/10) == 1
                X(i,:) = Best_X + W ;
            else
                X(i,:) = X(i,:) + W ;
            end
        else
            if rand > 0.5
                A = ub - abs(ub * t * sin(2 * pi * rand) / iter_max);
                R = (m(i) * e(i) + L(i) ^2) /dim * unifrnd( -A , A, 1, dim);
                X(i,:) = Best_X + R  + c * P(i,:) .* Best_X  ;
            else
                k = 0.5 + 0.5 * rand;
                B = ub - abs(ub * t * cos(2 * pi * rand) / iter_max);
                alpha = 1 / pi * exp((randi([0,t]) / iter_max));
                J = 2 * k * x(i)^2 * sin (2 * theta(i)) / m(i) / g * (1 - alpha) /dim  * unifrnd( -B , B, 1, dim);
                X(i,:) = Best_X + J + c * P(i,:) .* Best_X ;
            end
        end
    end

    X = boundaryCheck(X, lb, ub);
    Pop_Fit = feval(fhd,X',varargin{:});
    for i=1:pop_size
        if Pop_Fit(i)<Best_Score
            Best_Score=Pop_Fit(i);
            Best_X=X(i,:);
        end
    end

    convergence_curve(t)=Best_Score;
end
end


function [z] = Levy(n,m,beta)

    num = gamma(1+beta)*sin(pi*beta/2); % used for Numerator 
    
    den = gamma((1+beta)/2)*beta*2^((beta-1)/2); % used for Denominator

    sigma_u = (num/den)^(1/beta);% Standard deviation

    u = random('Normal',0,sigma_u,n,m); 
    
    v = random('Normal',0,1,n,m);

    z =u./(abs(v).^(1/beta));

  
  end

function [ X ] = boundaryCheck(X, lb, ub)
for i=1:size(X,1)
    FU=X(i,:)>ub;
    FL=X(i,:)<lb;
    X(i,:)=(X(i,:).*(~(FU+FL)))+ub.*FU+lb.*FL;
end
end

function X=initialization(SearchAgents_no,dim,ub,lb)

Boundary_no= size(ub,2); % numnber of boundaries

% If the boundaries of all variables are equal and user enter a signle
% number for both ub and lb
if Boundary_no==1
    X=rand(SearchAgents_no,dim).*(ub-lb)+lb;
end
% If each variable has a different lb and ub
if Boundary_no>1
    for i=1:dim
        ub_i=ub(i);
        lb_i=lb(i);
        X(:,i)=rand(SearchAgents_no,1).*(ub_i-lb_i)+lb_i;
    end
end
end
