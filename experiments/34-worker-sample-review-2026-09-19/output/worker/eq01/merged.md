And:

 $$ \begin{align*}\int q_{\boldsymbol{\theta}}(\mathbf{z})\log q_{\boldsymbol{\theta}}(\mathbf{z})d\mathbf{z}=&\int\mathcal{N}(\mathbf{z};\boldsymbol{\mu},\boldsymbol{\sigma}^{2})\log\mathcal{N}(\mathbf{z};\boldsymbol{\mu},\boldsymbol{\sigma}^{2})d\mathbf{z}\\ =&-\frac{J}{2}\log(2\pi)-\frac{1}{2}\sum_{j=1}^{J}(1+\log\sigma_{j}^{2})\end{align*} $$ 

Therefore:

 $$ \begin{align*}-D_{KL}((q_{\phi}(\mathbf{z})||p_{\boldsymbol{\theta}}(\mathbf{z}))&=\int q_{\boldsymbol{\theta}}(\mathbf{z})\left(\log p_{\boldsymbol{\theta}}(\mathbf{z})-\log q_{\boldsymbol{\theta}}(\mathbf{z})\right)d\mathbf{z}\\&=\frac{1}{2}\sum_{j=1}^{J}\left(1+\log((\sigma_{j})^{2})-(\mu_{j})^{2}-(\sigma_{j})^{2}\right)\end{align*} $$ 

When using a recognition model  $ q_{\phi}(\mathbf{z}|\mathbf{x}) $ then  $ \mu $ and s.d.  $ \sigma $ are simply functions of  $ \mathbf{x} $ and the variational parameters  $ \phi $, as exemplified in the text.

## C MLP's as probabilistic encoders and decoders

In variational auto-encoders, neural networks are used as probabilistic encoders and decoders. There are many possible choices of encoders and decoders, depending on the type of data and model. In our example we used relatively simple neural networks, namely multi-layered perceptrons (MLPs). For the encoder we used a MLP with Gaussian output, while for the decoder we used MLPs with either Gaussian or Bernoulli outputs, depending on the type of data.

## C.1 Bernoulli MLP as decoder

In this case let $p_{\theta}(\mathbf{x}|\mathbf{z})$ be a multivariate Bernoulli whose probabilities are computed from $\mathbf{z}$ with a fully-connected neural network with a single hidden layer:

 $$ \begin{aligned}\log p(\mathbf{x}|\mathbf{z})&=\sum_{i=1}^{D}x_{i}\log y_{i}+(1-x_{i})\cdot\log(1-y_{i})\\ where\mathbf{y}&=f_{\sigma}(\mathbf{W}_{2}\tanh(\mathbf{W}_{1}\mathbf{z}+\mathbf{b}_{1})+\mathbf{b}_{2})\end{aligned} $$ 

where  $ f_{\sigma}(.) $ is the elementwise sigmoid activation function, and where  $ \boldsymbol{\theta} = \{\mathbf{W}_1, \mathbf{W}_2, \mathbf{b}_1, \mathbf{b}_2\} $ are the weights and biases of the MLP.

## C.2 Gaussian MLP as encoder or decoder

In this case let encoder or decoder be a multivariate Gaussian with a diagonal covariance structure:

 $$ \begin{aligned}\log p(\mathbf{x}|\mathbf{z})&=\log\mathcal{N}(\mathbf{x};\boldsymbol{\mu},\boldsymbol{\sigma}^{2}\mathbf{I})\\ where\boldsymbol{\mu}&=\mathbf{W}_{4}\mathbf{h}+\mathbf{b}_{4}\\\log\boldsymbol{\sigma}^{2}&=\mathbf{W}_{5}\mathbf{h}+\mathbf{b}_{5}\\\mathbf{h}&=\tanh(\mathbf{W}_{3}\mathbf{z}+\mathbf{b}_{3})\end{aligned} $$ 

where $\{W_3, W_4, W_5, b_3, b_4, b_5\}$ are the weights and biases of the MLP and part of $\theta$ when used as decoder. Note that when this network is used as an encoder $q_{\phi}(\mathbf{z}|\mathbf{x})$, then $\mathbf{z}$ and $\mathbf{x}$ are swapped, and the weights and biases are variational parameters $\phi$.

### D Marginal likelihood estimator

We derived the following marginal likelihood estimator that produces good estimates of the marginal likelihood as long as the dimensionality of the sampled space is low (less than 5 dimensions), and sufficient samples are taken. Let  $ p_{\theta}(\mathbf{x}, \mathbf{z}) = p_{\theta}(\mathbf{z}) p_{\theta}(\mathbf{x}|\mathbf{z}) $ be the generative model we are sampling from, and for a given datapoint  $ \mathbf{x}^{(i)} $ we would like to estimate the marginal likelihood  $ p_{\theta}(\mathbf{x}^{(i)}) $.

The estimation process consists of three stages: